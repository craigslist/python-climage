#!/usr/bin/python
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

'''craigslist image package setuptools script.'''

import setuptools

import climage

setuptools.setup(
    name='climage',
    version=climage.__version__,
    description='craigslist image package',
    long_description=open('README.rst').read(),
    author='craigslist',
    author_email='opensource@craigslist.org',
    url='http://craigslist.org/about/opensource',
    packages=setuptools.find_packages(exclude=['test*']),
    scripts=[
        'bin/climageprocessor',
        'bin/climageserver'],
    test_suite='nose.collector',
    install_requires=[
        'clblob',
        'clcommon',
        'pgmagick',
        'PIL'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Topic :: Software Development :: Libraries :: Python Modules'])
