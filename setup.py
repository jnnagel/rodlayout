from setuptools import setup, find_packages

import rodlayout


with open('README.md') as fin:
    long_description = fin.read()

setup(
    name='rodlayout',
    version=rodlayout.__version__,
    author="Niels Buwen",
    author_email="dev@niels-buwen.de",
    description="A python wrapper for the Skill objects in virtuoso",
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    install_requires=[
        'geometry',
        'skillbridge'
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Intended Audience :: Developers",
        "Operating System :: POSIX :: Linux",
        "Topic :: Software Development",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
    ]
)
