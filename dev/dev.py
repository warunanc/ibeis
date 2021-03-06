#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dev.py was moved to ibeis/dev.py
Now runnable via python -m ibeis.dev
"""
from __future__ import absolute_import, division, print_function
# try:
#     from os.path import abspath, exists
#     newrelic_config_ini_filepath = abspath('newrelic.ini')
#     assert exists(newrelic_config_ini_filepath)
#     import newrelic.agent
#     newrelic.agent.initialize(newrelic_config_ini_filepath)
#     print('Using New Relic Agent: %r' % (newrelic.agent, ))
# except (ImportError, AssertionError):
#     print('Failed to initialize New Relic Performance Monitoring')
#     pass
from ibeis.dev import *  # NOQA

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    devmain()
