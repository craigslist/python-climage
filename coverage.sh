#!/bin/sh
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

echo "+++ Preparing to run coverage"
coverage=`which coverage`
if [ -z $coverage ]; then
    coverage=`which python-coverage`
    if [ -z $coverage ]; then
        echo 'Python coverage not found'
        exit 1
    fi
fi

cd `dirname "$0"`
export PYTHONPATH=".:$PYTHONPATH"
rm -rf coverage.html .coverage*
echo

echo "+++ Running test suite"
$coverage run -p setup.py nosetests
echo

echo "+++ Running commands"
image_config='
    --climage.processor.save=false
    --climage.processor.save_blob=false'
$coverage run -p climage/processor.py -n $image_config test/test.jpg
$coverage run -p climage/processor.py -n $image_config < test/test.jpg
echo

for signal in 2 9 15; do
    echo "+++ Testing climageserver shutdown with kill -$signal"
    $coverage run -p climage/server.py -n $image_config \
        --clcommon.http.port=12342 \
        --clcommon.log.syslog_ident=test \
        --clcommon.server.daemonize=true \
        --clcommon.server.pid_file=test_pid
    sleep 0.2
    kill -$signal `cat test_pid`
    sleep 1.2
    rm test_pid
done
echo

echo "+++ Generating coverage report"
$coverage combine
$coverage html -d coverage.html --include='climage/*'
$coverage report --include='climage/*'
