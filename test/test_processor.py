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

'''Tests for craigslist image processor module.'''

import json
import PIL.Image
import os
import shutil
import StringIO
import unittest

import clblob.client
import clcommon.config
import clcommon.http
import climage.processor

IMAGE = 'test/test.jpg'
EXIF_IMAGE = 'test/test_exif.jpg'
CONFIG = clcommon.config.update(climage.processor.DEFAULT_CONFIG, {
    'clblob': {
        'client': {
            'clusters': [[{"replicas": ["test"], "write_weight": 1}]],
            'replica': 'test',
            'replicas': {
                "test": {"ip": "127.0.0.1", "port": 12345, "read_weight": 0}}},
        'index': {
            'sqlite': {
                'database': 'test_blob/_index',
                'sync': 0}},
        'store': {
            'disk': {
                'path': 'test_blob',
                'sync': False}}}})


class TestProcessor(unittest.TestCase):

    config = CONFIG

    def __init__(self, *args, **kwargs):
        super(TestProcessor, self).__init__(*args, **kwargs)
        self.blob_servers = None

    def setUp(self):
        shutil.rmtree('test_blob', ignore_errors=True)
        os.makedirs('test_blob')

    def test_process(self):
        processor = climage.processor.Processor(self.config, open(IMAGE))
        processed = processor.process()
        self.assertEquals(processor.info['width'], 1000)
        self.assertEquals(processor.info['height'], 750)
        self.assertEquals(len(processed),
            len(self.config['climage']['processor']['sizes']))

    def test_convert(self):
        image = PIL.Image.open(open(IMAGE))
        output = StringIO.StringIO()
        image = image.convert(mode='LA')
        image.save(output, 'PNG')
        image = output.getvalue()
        processor = climage.processor.Processor(self.config, image)
        processed = processor.process()
        image = PIL.Image.open(StringIO.StringIO(processed['50x50c']))
        self.assertEquals(image.mode, 'RGB')

    def test_invalid_format(self):
        image = PIL.Image.open(open(IMAGE))
        output = StringIO.StringIO()
        image.save(output, 'PPM')
        image = output.getvalue()
        processor = climage.processor.Processor(self.config, image)
        self.assertRaises(climage.processor.BadImage, processor.process)

    def test_bad_file(self):
        processor = climage.processor.Processor(self.config, "bad")
        self.assertRaises(climage.processor.BadImage, processor.process)

    def test_too_large(self):
        config = clcommon.config.update_option(self.config,
            'climage.processor.max_width', 100)
        processor = climage.processor.Processor(config, open(IMAGE))
        self.assertRaises(climage.processor.BadImage, processor.process)

    def test_no_size(self):
        config = clcommon.config.update_option(self.config,
            'climage.processor.sizes', [])
        processor = climage.processor.Processor(config, open(IMAGE))
        processed = processor.process()
        self.assertEquals(len(processed), 0)

    def test_invalid_size(self):
        config = clcommon.config.update_option(self.config,
            'climage.processor.sizes', 'bad size')
        self.assertRaises(climage.processor.ProcessingError,
            climage.processor.Processor, config, open(IMAGE))

    def test_save_blob(self):
        processor = climage.processor.Processor(self.config, open(IMAGE))
        images = processor.process()
        self.assertTrue('blob_info_name' in processor.info)
        self.assertTrue('blob_names' in processor.info)
        client = clblob.client.Client(self.config)
        info = processor.info.copy()
        info.pop('blob_info_name')
        info.pop('blob_names')
        self.assertEquals(info,
            json.loads(client.get(processor.info['blob_info_name']).read()))
        for size in images:
            self.assertEquals(images[size],
                client.get(processor.info['blob_names'][size]).read())

    def test_save_blob_fail(self):
        config = clcommon.config.update_option(self.config,
            'clblob.client.replica', None)
        processor = climage.processor.Processor(config, open(IMAGE))
        self.assertRaises(clblob.RequestError, processor.process)

    def test_truncate(self):
        image = open(IMAGE).read()[:-100]
        processor = climage.processor.Processor(self.config, image)
        processed = processor.process()
        self.assertEquals(len(processed),
            len(self.config['climage']['processor']['sizes']))

    def test_pgmagick(self):
        # pylint: disable=W0212
        processor = climage.processor.Processor(self.config, open(IMAGE))
        processor._pgmagick()
        self.assertRaises(climage.processor.BadImage, processor._pgmagick)

    def test_exif(self):
        processor = climage.processor.Processor(self.config, open(EXIF_IMAGE))
        processor.process()
        self.assertEquals(processor.info['exif_gpsversionid'], '(2, 2, 0, 0)')


class TestProcessorNoThreads(TestProcessor):

    config = clcommon.config.update_option(CONFIG,
        'climage.processor.pool_size', 0)
