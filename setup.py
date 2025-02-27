"""Install openedx-webhooks."""

import re

from setuptools import find_packages, setup


# UPDATED VIA SEMGREP - if you need to remove/modify this method remove this line and add a comment specifying why
def is_requirement(line):
    """
    Return True if the requirement line is a package requirement.

    Returns:
        bool: True if the line is not blank, a comment,
        a URL, or an included file
    """
    return line and line.strip() and not line.startswith(('-r', '#', '-e', 'git+', '-c'))


def get_requirements(path):
    with open(path) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if is_requirement(line)]


version = ''
with open('openedx_webhooks/__init__.py', 'r') as fd:
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
    url="https://github.com/openedx/openedx_webhooks",
    packages=find_packages(),
    install_requires=get_requirements("requirements.txt"),
    license='Apache 2.0',
    classifiers=(
        'License :: OSI Approved :: Apache Software License',
        'Framework :: Flask',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.12',
    ),
    zip_safe=False,
)
