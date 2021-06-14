import os
import shutil
import sys
import subprocess
import glob
import numpy as np
from PIL import Image, ImageCms
from skimage.morphology import disk, binary_erosion
from skimage.filters import sobel, median
from skimage import segmentation



def get_extrema(im, im_size):
    # Produce downsized image from the green channel.
    small_size = (400, int(400 / (max(im_size) / min(im_size))))
    img_small = im.resize((small_size[im_size.index(max(im_size))],
                           small_size[im_size.index(min(im_size))]),
                          Image.BICUBIC,
                          reducing_gap = 1.0)
    img_small = np.asarray(img_small)
    img_small_grey = img_small[:, :, 1]

    # Use watershed to segment image into subject and background.
    edges = sobel(img_small_grey)
    markers = np.zeros_like(img_small_grey)
    markers[img_small_grey > 253] = 1
    markers[img_small_grey < 190] = 2
    subject_map = segmentation.watershed(edges, markers)
    subject_map[subject_map == 1] = 0
    subject_map[subject_map == 2] = 1
    subject_map = binary_erosion(subject_map, disk(6))

    # Find minimum and maximum values from median filtered image.
    selem = disk(1)
    img_small_r = median(img_small[:, :, 0], selem)
    img_small_g = median(img_small[:, :, 1], selem)

    subject_min = img_small.min()
    subject_max = max(img_small_r.max(initial = 0,
                                      where = subject_map),
                      img_small_g.max(initial = 0,
                                      where = subject_map))

    return (subject_min, subject_max)
        
def generate_lut(roi_min, roi_max):
    multiplier = 255 / (roi_max - roi_min)
    lut = []
    for ix in range(256):
        ix = int((ix - roi_min) * multiplier)
        if ix < 0:
            ix = 0
        elif ix > 255:
            ix = 255
        lut.append(ix)
    lut = lut + lut + lut

    return lut

def temp_cleanup(folder):
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))

def main():
    # Functional variables.
    folder = sys.argv[1:]
    temp_folder = 'Temp\\'
    temp_folder_abs = os.path.abspath(temp_folder)
    profile = ImageCms.ImageCmsProfile('ICC Profile\\'
                                       + 'sRGB Color Space Profile.icm')
    img_profile = profile.tobytes()
    
    # Delete last backup.
    temp_cleanup(temp_folder)

    for file_path in glob.glob(f'{folder[0]}/**/*.jpg', recursive = True):
        file_directory, file_name = os.path.split(file_path)
        relative_file_path = os.path.relpath(file_path, start = folder[0])
        temp_directory = os.path.join(temp_folder,
                                      os.path.dirname(relative_file_path))
        try:
            with Image.open(file_path) as img:
                try:
                    exif = dict(img._getexif().items())
                except AttributeError:
                    exif = {274: 1}
                img.load()
        except(FileNotFoundError, ValueError, TypeError, IOError,
               SyntaxError, IndexError):
            print(f'Problem loading {file_name}.')
            break

        # Correct for exif orientation.
        img_size = img.size
        if img_size[0] >= img_size[1]:
            if exif[274] == 3:
                img = img.transpose(method = Image.ROTATE_180)
            elif exif[274] == 6:
                img = img.transpose(method = Image.ROTATE_270)
            elif exif[274] == 8:
                img = img.transpose(method = Image.ROTATE_90)
            img_size = img.size

        # Move file to Temp folder.
        if not os.path.exists(temp_directory):
            os.mkdir(temp_directory)
        temp_file_name = os.path.join(temp_folder, relative_file_path)
        shutil.move(file_path, temp_file_name)

        minimum, maximum = get_extrema(img, img_size)

        img_norm = img.point(generate_lut(minimum, maximum))

        img_norm.save(file_path,
                      quality = 95,
                      dpi = (300, 300),
                      icc_profile = img_profile)
        print(f'{file_name} saved.')

    # Batch copy the metadata from the backup files to the cropped files.
    print('\nReinstating metadata.')
    try:
        subprocess.run('exiftool -ext JPG -tagsfromfile '
                       + f'"{temp_folder_abs}/%d/%f.%e" -all:all '
                       + '--IFD0:Orientation --ThumbnailImage '
                       + '-overwrite_original -r .',
                       shell = False, stdout = subprocess.DEVNULL,
                       stderr = subprocess.STDOUT, cwd = folder[0])
        print('\nMetadata successfully added.')
    except:
        print('\nThere was a problem reinstating the metadata')

    input('\nFolder complete. Press enter to exit.')


if __name__ == '__main__':
    main()

