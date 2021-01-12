"""Install openedx-webhooks."""

import re

from setuptools import find_packages, setup


def is_requirement(line):
    line = line.strip()
    # Skip blank lines, comments, and editable installs
    return not (
        line == '' or
        line.startswith('--') or
        line.startswith('-r') or
        line.startswith('#') or
        line.startswith('-e') or
        line.startswith('git+')
    )


def get_requirements(path):
    with open(path) as f:
        lines = f.readlines()
    return [l.strip() for l in lines if is_requirement(l)]


version = ''
with open('openedx_webhooks/__init__.py') as fd:
    version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
                        fd.read(), re.MULTILINE).group(1)

if not version:
    raise RuntimeError('Cannot find version information')


setup(
    name="openedx_webhooks",
    version=version,
    description="Automated tasks for Open edX",
    long_description=open('README.rst').read(),
    author="Open Source Community Managers at edX",
    author_email="oscm@edx.org",
    url="https://github.com/edx/openedx_webhooks",
    packages=find_packages(),
    install_requires=get_requirements("requirements.txt"),
    license='Apache 2.0',
    classifiers=(
        'License :: OSI Approved :: Apache Software License',
        'Framework :: Flask',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.8',
    ),
    zip_safe=False,
)
