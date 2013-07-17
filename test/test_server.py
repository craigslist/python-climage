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

'''Tests for craigslist image server module.'''

import httplib
import json
import os.path
import PIL.Image
import shutil
import StringIO
import unittest

import clcommon.config
import clcommon.http
import climage.server
import test.test_processor

HOST = '127.0.0.1'
PORT = 8123
CONFIG = clcommon.config.update(climage.server.DEFAULT_CONFIG, {
    'clcommon': {
        'http': {
            'host': HOST,
            'port': PORT}}})
CONFIG = clcommon.config.update(CONFIG, test.test_processor.CONFIG)
IMAGE = open(test.test_processor.IMAGE).read()


def request(method, url, *args, **kwargs):
    '''Perform the request and handle the response.'''
    connection = httplib.HTTPConnection(HOST, PORT)
    connection.request(method, url, *args, **kwargs)
    return connection.getresponse()


class TestServer(unittest.TestCase):

    server_class = climage.server.Server
    request_class = climage.server.Request

    def __init__(self, *args, **kwargs):
        super(TestServer, self).__init__(*args, **kwargs)
        self.server = None

    def start_server(self, config=None):
        '''Start the server, stopping an old one if needed.'''
        config = config or CONFIG
        self.stop_server()
        self.server = climage.server.Server(config, climage.server.Request)
        self.server.start()

    def stop_server(self):
        '''Stop the server if running.'''
        if self.server is not None:
            self.server.stop()
            self.server = None

    def setUp(self):
        shutil.rmtree('test_blob', ignore_errors=True)
        os.makedirs('test_blob')
        self.start_server()

    def tearDown(self):
        self.stop_server()

    def test_methods(self):
        response = request('GET', '/')
        self.assertEquals(405, response.status)
        response = request('DELETE', '/')
        self.assertEquals(405, response.status)
        response = request('PUT', '/')
        self.assertEquals(415, response.status)
        response = request('POST', '/')
        self.assertEquals(415, response.status)

    def test_bad_data(self):
        config = clcommon.config.update_option(CONFIG,
            'climage.server.save_bad_path', 'test_image_bad')
        self.start_server(config)
        shutil.rmtree('test_image_bad', ignore_errors=True)
        response = request('PUT', '/?filename=a/b\x00\x80/%s' % ('c' * 1000),
            'bad data')
        self.assertEquals(415, response.status)
        self.assertEquals(True, os.path.isdir('test_image_bad'))
        self.assertNotEquals(0, len(os.listdir('test_image_bad')))

    def test_no_sizes(self):
        response = request('PUT', '/?sizes=', IMAGE)
        self.assertEquals(200, response.status)

    def test_response_default(self):
        response = request('PUT', '/', IMAGE)
        self.assertEquals(200, response.status)
        self.assertEquals(64, len(response.read()))
        self.assertEquals('text/plain', response.getheader('Content-Type'))

    def test_response_none(self):
        response = request('PUT', '/?response=none', IMAGE)
        self.assertEquals(0, len(response.read()))
        self.assertEquals(200, response.status)

    def test_response_checksum(self):
        response = request('PUT', '/?response=checksum', IMAGE)
        self.assertEquals(200, response.status)
        self.assertEquals(64, len(response.read()))
        self.assertEquals('text/plain', response.getheader('Content-Type'))

    def test_response_info(self):
        response = request('PUT', '/?response=info', IMAGE)
        self.assertEquals(200, response.status)
        self.assertEquals('application/json',
            response.getheader('Content-Type'))
        info = json.loads(response.read())
        self.assertEquals(64, len(info['checksum']))

    def test_response_image(self):
        response = request('PUT', '/?response=50x50c', IMAGE)
        self.assertEquals(200, response.status)
        self.assertNotEquals(0, len(response.read()))
        self.assertEquals('image/jpeg', response.getheader('Content-Type'))

    def test_response_bad(self):
        response = request('PUT', '/?response=bad', IMAGE)
        self.assertEquals(400, response.status)

    def test_invalid_format(self):
        image = PIL.Image.open(open(test.test_processor.IMAGE))
        output = StringIO.StringIO()
        image.save(output, 'PPM')
        response = request('PUT', '/', output.getvalue())
        self.assertEquals(415, response.status)

    def test_too_large(self):
        config = clcommon.config.update_option(CONFIG,
            'climage.processor.max_width', 100)
        self.start_server(config)
        response = request('PUT', '/', IMAGE)
        self.assertEquals(415, response.status)

    def test_param_sizes(self):
        response = request('PUT', '/?sizes=20x20,50x50c', IMAGE)
        self.assertEquals(200, response.status)
        response = request('PUT', '/?sizes=', IMAGE)
        self.assertEquals(200, response.status)
        response = request('PUT', '/?sizes=bad', IMAGE)
        self.assertEquals(400, response.status)

    def test_param_ttl(self):
        response = request('PUT', '/?ttl=100', IMAGE)
        self.assertEquals(200, response.status)

    def test_param_quality(self):
        response = request('PUT', '/?quality=10', IMAGE)
        self.assertEquals(200, response.status)

    def test_param_save(self):
        response = request('PUT', '/?save=true', IMAGE)
        self.assertEquals(200, response.status)
        response = request('PUT', '/?save=false', IMAGE)

    def test_param_filename(self):
        response = request('PUT', '/?filename=test', IMAGE)
        self.assertEquals(200, response.status)
