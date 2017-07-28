# coding=utf-8
"""Tests that CRUD RPM repositories.

For information on repository CRUD operations, see `Creation, Deletion and
Configuration
<http://docs.pulpproject.org/en/latest/dev-guide/integration/rest-api/repo/cud.html>`_.
"""
import os
import unittest
from urllib.parse import urljoin

import requests
from packaging import version

from pulp_smash import api, cli, selectors, utils
from pulp_smash.constants import (
    REPOSITORY_GROUP_PATH,
    REPOSITORY_PATH,
    RPM_SIGNED_FEED_URL,
    PYTHON_PYPI_FEED_URL,
    PUPPET_MODULE_URL_2,
)
from pulp_smash.tests.rpm.api_v2.utils import (
    gen_distributor as gen_rpm_distributor,
    gen_repo as gen_rpm_repo
)

from pulp_smash.tests.python.api_v2.utils import (
    gen_repo as gen_python_repo,
    gen_distributor as gen_python_distributor
)

from pulp_smash.tests.puppet.api_v2.utils import (
    gen_repo as gen_puppet_repo,
    gen_distributor as gen_puppet_distributor
)

class PopulateRPMRepo(utils.BaseAPITestCase):
    """Create an RPM repo that is synced and published."""

    def test_all(self):
        client = api.Client(self.cfg, api.json_handler)
        distributor = gen_rpm_distributor()
        distributor['auto_publish'] = True
        body = gen_rpm_repo()
        body['distributors'] = [distributor]
        body['importer_config'] = {
            'feed': RPM_SIGNED_FEED_URL,
        }
        body['display_name'] = 'rpm-signed'
        body['id'] = body['display_name']
        repo = client.post(REPOSITORY_PATH, body)
        utils.sync_repo(self.cfg, repo)


class PopulatePythonRepo(utils.BaseAPITestCase):
    """Create a RPM repo that is synced and published."""

    def test_all(self):
        client = api.Client(self.cfg, api.json_handler)
        distributor = gen_python_distributor()
        distributor['auto_publish'] = True
        body = gen_python_repo()
        body['distributors'] = [distributor]
        body['importer_config'] = {
            'feed': PYTHON_PYPI_FEED_URL,
        }
        body['display_name'] = 'pypi'
        body['id'] = body['display_name']
        repo = client.post(REPOSITORY_PATH, body)
        utils.sync_repo(self.cfg, repo)


class PopulatePuppetRepo(utils.BaseAPITestCase):
    """Create a Puppet repo that is synced and published."""

    def test_all(self):
        client = api.Client(self.cfg, api.json_handler)
        distributor = gen_puppet_distributor()
        distributor['auto_publish'] = True
        body = gen_puppet_repo()
        body['distributors'] = [distributor]
        body['importer_config'] = {
            'feed': PUPPET_MODULE_URL_2,
        }
        body['display_name'] = 'puppetforge'
        body['id'] = body['display_name']
        repo = client.post(REPOSITORY_PATH, body)
        utils.sync_repo(self.cfg, repo)
