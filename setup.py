#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError :
    raise ImportError("setuptools module required, please go to https://pypi.python.org/pypi/setuptools and follow the instructions for installing setuptools")

setup(
    name='openelex',
    version='0.0.1',
    include_package_data=True,
    install_requires=[
        'python-dateutil',
        'scrapelib==1.0.0',
        'lxml==3.4.4',
    ],
)
