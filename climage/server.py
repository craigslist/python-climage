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

'''craigslist image server module.

This is a thin HTTP server layer around the image processor class. This
adds the ability to save any failed images for later inspection and to
return either the info or any size image that was requested after being
processed. This maintains a worker pool and blob client that is shared
between all requests.'''

import json
import os
import time

import clblob.client
import clcommon.config
import clcommon.http
import clcommon.server
import clcommon.worker
import climage.processor

DEFAULT_CONFIG = clcommon.config.update(climage.processor.DEFAULT_CONFIG,
    clcommon.http.DEFAULT_CONFIG)
DEFAULT_CONFIG = clcommon.config.update(DEFAULT_CONFIG, {
    'climage': {
        'server': {
            'response': 'checksum',
            'save_bad_path': None}}})

DEFAULT_CONFIG_FILES = climage.processor.DEFAULT_CONFIG_FILES + [
    '/etc/climageserver.conf',
    '~/.climageserver.conf']
DEFAULT_CONFIG_DIRS = climage.processor.DEFAULT_CONFIG_DIRS + [
    '/etc/climageserver.d',
    '~/.climageserver.d']


VALID_RESPONSES = ['none', 'checksum', 'info']


class Request(clcommon.http.Request):
    '''Request handler for image processing.'''

    def run(self):
        '''Run the request.'''
        if self.method not in ['POST', 'PUT']:
            raise clcommon.http.MethodNotAllowed()
        config = self.parse_params(['filename'], ['quality', 'ttl'],
            ['save', 'save_blob'], ['sizes'])
        config = clcommon.config.update(self.server.config,
            {'climage': {'processor': config}})
        response = config['climage']['server']['response']
        response = self.params.get('response', response).lower()
        sizes = config['climage']['processor']['sizes']
        if response not in VALID_RESPONSES + sizes:
            raise clcommon.http.BadRequest(
                _('Invalid response parameter: %s') % response)
        try:
            processor = climage.processor.Processor(config, self.body_data,
                self.server.image_processor_pool, self.server.blob_client)
            processed = processor.process()
        except climage.processor.ProcessingError, exception:
            raise clcommon.http.BadRequest(str(exception))
        except climage.processor.BadImage, exception:
            self.log.warning(_('Bad image file: %s%s'), exception,
                self._save_bad())
            raise clcommon.http.UnsupportedMediaType(_('Bad image file'))
        body = None
        if response == 'checksum':
            body = processor.info['checksum']
            self.headers.append(('Content-type', 'text/plain'))
        elif response == 'info':
            body = json.dumps(processor.info)
            self.headers.append(('Content-type', 'application/json'))
        elif response in sizes:
            body = processed[response]
            self.headers.append(('Content-type', 'image/jpeg'))
        return self.ok(body)

    def _save_bad(self):
        '''Save bad image file to some location if enabled.'''
        path = self.server.config['climage']['server']['save_bad_path']
        if path is None:
            return ''
        try:
            if not os.path.isdir(path):
                os.makedirs(path)
            filename = self.params.get('filename', '')
            filename = ''.join(char for char in filename
                if 32 < ord(char) < 127 and char != '/')
            filename = '%f.%s' % (time.time(), filename)
            filename = os.path.join(path, filename[:100])
            bad_file = open(filename, 'w')
            bad_file.write(self.body_data)
            bad_file.close()
            return ' (%s)' % filename
        except Exception, exception:
            self.log.warning(_('Could not save bad file: %s'), exception)
            return ''


class Server(clcommon.http.Server):
    '''Wrapper for the HTTP server that adds an image processing pool so
    we can use it across all requests.'''

    def __init__(self, config, request):
        super(Server, self).__init__(config, request)
        self.blob_client = None
        self.image_processor_pool = None

    def start(self):
        if self.config['climage']['processor']['save_blob']:
            self.blob_client = clblob.client.Client(self.config)
        self.image_processor_pool = clcommon.worker.Pool(
            self.config['climage']['processor']['pool_size'])
        super(Server, self).start()

    def stop(self, timeout=None):
        super(Server, self).stop(timeout)
        if self.blob_client is not None:
            self.blob_client.stop()
            self.blob_client = None
        self.image_processor_pool.stop()
        self.image_processor_pool = None


if __name__ == '__main__':
    clcommon.server.Server(DEFAULT_CONFIG, DEFAULT_CONFIG_FILES,
        DEFAULT_CONFIG_DIRS, [lambda config: Server(config, Request)]).start()
