..
  Copyright 2013 craigslist
 
  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at
 
      http://www.apache.org/licenses/LICENSE-2.0
 
  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

This is the craigslist image python package. It contains an image
processing library, tool, and server. For full documentation, run pydoc
on the command line with package and module names::

    pydoc climage

An HTML version of the documentation can also be built. Once complete,
point a browser to: doc/_build/html/index.html::

    python setup.py build_sphinx

To install the package (use --prefix option for a specific location)::

    python setup.py install

To run the test suite::

    python setup.py nosetests

If python-coverage is installed, text and HTML code coverage reports can
be generated for the test suite and command line programs by running::

    ./coverage.sh

There are a number of code style checks already in place using the tools
below. While they are good settings for now, don't hesitate to bring up
any violations encountered for discussion if it should be allowed. To
run the checks::

    pylint -iy --rcfile .pylintrc climage test setup.py
    pep8 --ignore=E128 -r .
    pyflakes . | grep -v "undefined name '_'"

To build a source tarball for distribution (see 'dist' directory after)::

    python setup.py sdist
