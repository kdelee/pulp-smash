# coding=utf-8
"""Tests that remove repos from a populated server.

To remove content generated by pulp_migrate.populate tests, run these test cases
in pulp_migrate.clean. These tests will only remove content if it is present.

"""
from urllib.parse import urljoin

import unittest

from pulp_smash import api, utils, config

from pulp_migrate.utils import clean_repo

from pulp_migrate.constants import (
    RPM_REPO,
    PYTHON_REPO,
    PUPPET_REPO,
    DOCKER_V1_REPO,
    DOCKER_V2_REPO,
)

class CleanRepos(unittest.TestCase):
    """Delete populated repositories."""

    def test_clean_rpm(self):
        clean_repo(RPM_REPO)

    def test_clean_python(self):
        clean_repo(PYTHON_REPO)

    def test_clean_dockerv1(self):
        clean_repo(DOCKER_V1_REPO)

    def test_clean_dockerv2(self):
        clean_repo(DOCKER_V2_REPO)
