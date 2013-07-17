# Copyright 2013 craigslist
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''craigslist image processor module.

This provides a processor class that can be run on the command line or
called through the server module.'''

import hashlib
import json
import pgmagick
import PIL.Image
import PIL.ImageFile
import re
import StringIO
import sys
import time

import clblob.client
import clcommon.config
import clcommon.log
import clcommon.profile
import clcommon.worker
import climage.exif

# Increase max blocks in ImageFile lib to allow for saving larger images.
PIL.ImageFile.MAXBLOCK = 1048576

DEFAULT_CONFIG = clcommon.config.update(clblob.client.DEFAULT_CONFIG, {
    'climage': {
        'processor': {
            'formats': ['TIFF', 'BMP', 'JPEG', 'GIF', 'PNG'],
            'log_level': 'NOTSET',
            'max_height': 7000,
            'max_width': 7000,
            'pool_size': 8,
            'quality': 70,
            'save': True,
            'save_blob': True,
            'sizes': ['50x50c', '300x300', '600x450'],
            'ttl': 7776000}}})  # 90 days

DEFAULT_CONFIG_FILES = clblob.client.DEFAULT_CONFIG_FILES + [
    '/etc/climageprocessor.conf',
    '~/.climageprocessor.conf']
DEFAULT_CONFIG_DIRS = clblob.client.DEFAULT_CONFIG_DIRS + [
    '/etc/climageprocessor.d',
    '~/.climageprocessor.d']

SIZE_REGEX = re.compile('^([0-9]+)x([0-9]+)(.*)')

ORIENTATION_OPERATIONS = {
    1: [],
    2: [PIL.Image.FLIP_LEFT_RIGHT],
    3: [PIL.Image.ROTATE_180],
    4: [PIL.Image.FLIP_TOP_BOTTOM],
    5: [PIL.Image.FLIP_TOP_BOTTOM, PIL.Image.ROTATE_270],
    6: [PIL.Image.ROTATE_270],
    7: [PIL.Image.FLIP_LEFT_RIGHT, PIL.Image.ROTATE_270],
    8: [PIL.Image.ROTATE_90]}


class Processor(object):
    '''Image processing class. This handles a processing job for a single
    image. An optional worker pool and blob client can be passed in for
    use between different processor objects.'''

    def __init__(self, config, image, pool=None, blob_client=None):
        self.config = config['climage']['processor']
        self._pool = pool or clcommon.worker.Pool(self.config['pool_size'])
        self._stop_pool = pool is None
        if self.config['save_blob'] and blob_client is None:
            blob_client = clblob.client.Client(config)
        self._blob_client = blob_client
        self.log = clcommon.log.get_log('climage_processor',
            self.config['log_level'])
        self.profile = clcommon.profile.Profile()
        if not isinstance(image, str):
            image = image.read()
            self.profile.mark_time('read')
        self.raw = image
        self.profile.mark('original_size', len(self.raw))
        self._pgmagick_ran = False
        self._processed = {}
        self.info = {}
        self._orientation = 1
        self._sizes = []
        for size in self.config['sizes']:
            match = SIZE_REGEX.match(size)
            if match is None:
                raise ProcessingError(_('Invalid size parameter: %s') % size)
            parsed_size = dict(name=size)
            parsed_size['width'] = int(match.group(1))
            parsed_size['height'] = int(match.group(2))
            parsed_size['flags'] = match.group(3)
            self._sizes.append(parsed_size)

    def __del__(self):
        if hasattr(self, '_pool') and self._stop_pool:
            self._pool.stop()
        if hasattr(self, 'profile') and len(self.profile.marks) > 0:
            self.log.info('profile %s', self.profile)

    def process(self):
        '''Process the image as specified in the config. Image info
        (such as the blob names after being saved) can be found in the
        info attribute when this returns. This returns a dictionary of
        resized images, indexed by the size name from the config.'''
        self.profile.reset_time()
        start = time.time()
        image = self._pool.start(self._load).wait()
        batch = self._pool.batch()
        for size in self._sizes:
            batch.start(self._process, size, image)
            image = None
        batch.wait_all()
        self.profile.reset_time()
        if self.config['save']:
            if self.config['save_blob']:
                self._save_blob()
        self.profile.mark('real_time', time.time() - start)
        return self._processed

    def _load(self):
        '''Load image and parse info.'''
        try:
            image = PIL.Image.open(StringIO.StringIO(self.raw))
        except Exception:
            self.profile.mark_time('open')
            try:
                self._pgmagick()
                image = PIL.Image.open(StringIO.StringIO(self.raw))
            except Exception, exception:
                raise BadImage(_('Cannot open image: %s') % exception)
        self.profile.mark_time('open')

        self._get_info(image)
        self._check_info(self.info)

        self._orientation = int(self.info.get('exif_orientation', 1))
        if self._orientation not in ORIENTATION_OPERATIONS:
            self._orientation = 1

        if len(self._sizes) == 0:
            return image

        # Fix width and height to keep aspect ration for non-cropped images.
        for size in self._sizes:
            if 'c' in size['flags']:
                continue
            width, height = image.size
            if self._orientation > 4:
                # Width and height will be reversed for these orientations.
                width, height = height, width
            if width > size['width']:
                height = max(height * size['width'] / width, 1)
                width = size['width']
            if height > size['height']:
                width = max(width * size['height'] / height, 1)
                height = size['height']
            size['width'], size['height'] = width, height

        try:
            self._load_image(image, self._sizes[0])
        except Exception:
            self.profile.mark_time('load')
            try:
                self._pgmagick()
                image = PIL.Image.open(StringIO.StringIO(self.raw))
                self.profile.mark_time('open')
                self._load_image(image, self._sizes[0])
            except Exception, exception:
                raise BadImage(_('Cannot load image: %s') % exception)
        self.profile.mark_time('load')

        return image

    def _load_image(self, image, size):
        '''Load the image using the smallest sample we can.'''
        width, height = size['width'], size['height']
        if self._orientation > 4:
            # Width and height will be reversed for these orientations.
            width, height = height, width
        image.draft(None, (width, height))
        image.load()

    def _get_info(self, image):
        '''Parse out all info and exif data embedded in image.'''
        for key, value in image.info.iteritems():
            if key == 'exif' and hasattr(image, '_getexif'):
                self._get_exif(image)
            else:
                self._set_info(key, value)
        if 'filename' in self.config:
            self.info['filename'] = self.config['filename']
        self.info['width'] = image.size[0]
        self.info['height'] = image.size[1]
        self.info['format'] = image.format
        self.info['mode'] = image.mode
        self.profile.mark_time('info')
        value = hashlib.sha256(self.raw).hexdigest()  # pylint: disable=E1101
        self.info['checksum'] = value
        self.profile.mark_time('checksum')

    def _get_exif(self, image):
        '''Add exif data to the info dictionary.'''
        try:
            exif = image._getexif()  # pylint: disable=W0212
        except Exception:
            return
        for key, value in exif.items():
            key = climage.exif.TAGS.get(key, key)
            if key == 'GPSTag':
                for gps_key, gps_value in value.items():
                    gps_key = climage.exif.GPSINFO_TAGS.get(gps_key, gps_key)
                    self._set_info('exif_%s' % gps_key, gps_value)
            else:
                self._set_info('exif_%s' % key, value)

    def _set_info(self, key, value):
        '''Set an info key value pair if it is UTF-8 safe.'''
        try:
            value = str(value)
            value = value.replace('\x00', '')
            value.encode('utf-8')
            if len(value) > 1024:
                self.log.debug(_('Value too large for info key: %s(%d'), key,
                    len(value))
                return
            self.info[str(key).lower()] = value
        except UnicodeError:
            self.log.debug(_('Value not UTF-8 safe for info key: %s'), key)

    def _check_info(self, info):
        '''Make sure image is allowed with given info.'''
        if info['format'] == '':
            raise BadImage(_('Unknown image format'))
        if info['format'] not in self.config['formats']:
            raise BadImage(_('Invalid image format: %s') % info['format'])
        if info['width'] > self.config['max_width'] or \
                info['height'] > self.config['max_height']:
            raise BadImage(_('Image too large: %dx%d') %
                (info['width'], info['height']))

    def _process(self, size, image=None):
        '''Process a given image size.'''
        profile = clcommon.profile.Profile()

        # Used image.copy originally, but that was actually much slower than
        # reopening unless the image has already been modified in some way.
        if image is None:
            image = PIL.Image.open(StringIO.StringIO(self.raw))
            profile.mark_time('open')
            try:
                self._load_image(image, size)
            except Exception, exception:
                profile.mark_time('load')
                raise BadImage(_('Cannot load image (proc): %s') % exception)
            profile.mark_time('load')

        width, height = size['width'], size['height']
        if 'c' in size['flags']:
            image = self._crop(image, width, height)
            profile.mark_time('%s:crop' % size['name'])

        if self._orientation > 4:
            # Width and height will be reversed for these orientations.
            width, height = height, width
        image = image.resize((width, height), PIL.Image.ANTIALIAS)
        profile.mark_time('%s:resize' % size['name'])

        if self._orientation > 1:
            for operation in ORIENTATION_OPERATIONS[self._orientation]:
                image = image.transpose(operation)
            profile.mark_time('%s:transpose' % size['name'])

        if image.mode in ['P', 'LA']:
            image = image.convert(mode='RGB')
            profile.mark_time('%s:convert' % size['name'])

        output = StringIO.StringIO()
        image.save(output, 'JPEG', quality=self.config['quality'],
            optimize=True)
        raw = output.getvalue()
        self._processed[size['name']] = raw
        profile.mark_time('%s:save' % size['name'])
        profile.mark('%s:size' % size['name'], len(raw))
        self.profile.update(profile)

    def _crop(self, image, end_width, end_height):
        '''Crop the image if needed.'''
        width, height = image.size
        if self._orientation > 4:
            # Width and height will be reversed for these orientations.
            width, height = height, width
        factor = min(float(width) / end_width, float(height) / end_height)
        crop_width = int(end_width * factor)
        crop_height = int(end_height * factor)
        left = (width - crop_width) / 2
        upper = (height - crop_height) / 2
        right = left + crop_width
        lower = upper + crop_height
        if self._orientation > 4:
            left, upper = upper, left
            right, lower = lower, right
        return image.crop((left, upper, right, lower))

    def _pgmagick(self):
        '''When an error is encountered while opening an image, run
        it through pgmagick since it is a lot more forgiving of errors
        (truncation, bad headers, etc). This seems to be rare, but this
        way we can process more things successfully. We want to still
        use PIL for all other operations we perform since they are faster
        than pgmagick.'''
        if self._pgmagick_ran:
            raise BadImage(_('Already converted with pgmagick'))
        self._pgmagick_ran = True
        blob = pgmagick.Blob(self.raw)
        image = pgmagick.Image()
        image.ping(blob)
        self._check_info(dict(format=image.magick(), width=image.columns(),
            height=image.rows()))
        image = pgmagick.Image(blob)
        image.quality(self.config['quality'])
        blob = pgmagick.Blob()
        image.write(blob)
        self.raw = blob.data
        self.profile.mark_time('pgmagick')
        self.profile.mark('pgmagick_size', len(self.raw))

    def _save_blob(self):
        '''Save the image to the blob service.'''
        checksum = int(self.info['checksum'][:16], 16)
        checksum = clcommon.anybase.encode(checksum, 62)
        name = self._blob_client.name(checksum)
        pool = clcommon.worker.Pool(4, True)
        batch = pool.batch()
        batch.start(self._blob_client.put, '%s.json' % name,
            json.dumps(self.info), self.config['ttl'], encoded=True)
        self.info['blob_info_name'] = '%s.json' % name
        self.info['blob_names'] = {}
        for size in self._processed:
            batch.start(self._blob_client.put, '%s_%s.jpg' % (name, size),
                self._processed[size], self.config['ttl'], encoded=True)
            self.info['blob_names'][size] = '%s_%s.jpg' % (name, size)
        batch.wait_all()
        pool.stop()
        self.log.info('save_blob_name: %s', name)
        self.profile.mark_time('save_blob')


class ProcessingError(Exception):
    '''Exception raised when a processing error is encountered.'''

    pass


class BadImage(Exception):
    '''Exception raised when a bad image is encountered.'''

    pass


def _main():
    '''Run the image tool.'''
    config = clcommon.config.update(DEFAULT_CONFIG,
        clcommon.log.DEFAULT_CONFIG)
    config, filenames = clcommon.config.load(config, DEFAULT_CONFIG_FILES,
        DEFAULT_CONFIG_DIRS)
    clcommon.log.setup(config)
    if len(filenames) == 0:
        filenames = ['-']
    for filename in filenames:
        if filename == '-':
            image = sys.stdin
        else:
            config = clcommon.config.update_option(config,
                'climage.processor.filename', filename)
            print filename
            image = open(filename)
        processor = Processor(config, image)
        processed = processor.process()
        for key in processed:
            print '%s: %s' % (key, len(processed[key]))
        print
        for key in sorted(processor.info):
            print '%s: %s' % (key, processor.info[key])
        print
        print


if __name__ == '__main__':
    _main()
