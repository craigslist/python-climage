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

'''craigslist image package.

This provides tools and a server for processing images. Specifically, it
resizes, crops, rotates according to EXIF data tags for multiple sizes,
and then stores it into the blob service. The server provides a simple
HTTP interface for clients to submit the original image and options to.'''

# Install the _(...) function as a built-in so all other modules don't need to.
import gettext
gettext.install('climage')

__version__ = '0'
