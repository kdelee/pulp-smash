# coding=utf-8
"""Tests for syncing and publishing docker repositories."""
import unittest
from urllib.parse import urlsplit, urlunsplit

from jsonschema import validate
from packaging.version import Version

from pulp_smash import api, cli, config, selectors, utils
from pulp_smash.constants import (
    DOCKER_V1_FEED_URL,
    DOCKER_V2_FEED_URL,
    REPOSITORY_PATH,
)
from pulp_smash.tests.docker.api_v2.utils import gen_distributor, gen_repo
from pulp_smash.tests.docker.utils import get_upstream_name
from pulp_smash.tests.docker.utils import set_up_module  # noqa pylint:disable=unused-import

# Variable name derived from HTTP content-type.
MANIFEST_V1 = {
    '$schema': 'http://json-schema.org/schema#',
    'title': 'Image Manifest Version 2, Schema 1',
    'description': (
        'Derived from: '
        'https://docs.docker.com/registry/spec/manifest-v2-1/'
    ),
    'type': 'object',
    'properties': {
        'architecture': {'type': 'string'},
        'fsLayers': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'blobSum': {'type': 'string'}},
            },
        },
        'history': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'v1Compatibility': {'type': 'string'}},
            },
        },
        'name': {'type': 'string'},
        'schemaVersion': {'type': 'integer'},
        'signatures': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'header': {
                        'type': 'object',
                        'properties': {
                            'jwk': {
                                'type': 'object',
                                'properties': {
                                    'crv': {'type': 'string'},
                                    'kid': {'type': 'string'},
                                    'kty': {'type': 'string'},
                                    'x': {'type': 'string'},
                                    'y': {'type': 'string'},
                                },
                            },
                            'alg': {'type': 'string'},
                        },
                    },
                    'protected': {'type': 'string'},
                    'signature': {'type': 'string'},
                },
            },
        },
        'tag': {'type': 'string'},
    },
}
"""A schema for docker v2 image manifests, schema 1."""

# Variable name derived from HTTP content-type.
MANIFEST_V2 = {
    '$schema': 'http://json-schema.org/schema#',
    'title': 'Image Manifest Version 2, Schema 2',
    'description': (
        'Derived from: '
        'https://docs.docker.com/registry/spec/manifest-v2-2/#image-manifest'
    ),
    'type': 'object',
    'properties': {
        'config': {
            'type': 'object',
            'properties': {
                'digest': {'type': 'string'},
                'mediaType': {'type': 'string'},
                'size': {'type': 'integer'},
            },
        },
        'layers': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'digest': {'type': 'string'},
                    'mediaType': {'type': 'string'},
                    'size': {'type': 'integer'},
                    'urls': {
                        'type': 'array',
                        'items': {'type': 'string'},
                    },
                },
            },
        },
        'mediaType': {'type': 'string'},
        'schemaVersion': {'type': 'integer'},
    },
}
"""A schema for docker v2 image manifests, schema 2."""

# Variable name derived from HTTP content-type.
MANIFEST_LIST_V2 = {
    '$schema': 'http://json-schema.org/schema#',
    'title': 'Image Manifest List',
    'description': (
        'Derived from: '
        'https://docs.docker.com/registry/spec/manifest-v2-2/#manifest-list'
    ),
    'type': 'object',
    'properties': {
        'schemaVersion': {'type': 'integer'},
        'mediaType': {'type': 'string'},
        'manifests': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'mediaType': {'type': 'string'},
                    'size': {'type': 'integer'},
                    'digest': {'type': 'string'},
                    'platform': {
                        'type': 'object',
                        'properties': {
                            'architecture': {'type': 'string'},
                            'os': {'type': 'string'},
                            'os.version': {'type': 'string'},
                            'os.features': {
                                'type': 'array',
                                'items': {'type': 'string'},
                            },
                            'variant': {'type': 'string'},
                            'features': {
                                'type': 'array',
                                'items': {'type': 'string'},
                            }
                        }
                    }
                }
            }
        }
    }
}
"""A schema for docker manifest lists."""


class SyncPublishMixin(object):
    """Tools for test cases that sync and publish Docker repositories.

    This class must be mixed in to a class that inherits from
    ``unittest.TestCase``.
    """

    @staticmethod
    def adjust_url(url):
        """Return a URL that can be used for talking with Crane.

        The URL returned is the same as ``url``, except that the scheme is set
        to HTTP, and the port is set to (or replaced by) 5000.

        :param url: A string, such as ``https://pulp.example.com/foo``.
        :returns: A string, such as ``http://pulp.example.com:5000/foo``.
        """
        parse_result = urlsplit(url)
        netloc = parse_result[1].partition(':')[0] + ':5000'
        return urlunsplit(('http', netloc) + parse_result[2:])

    @staticmethod
    def make_crane_client(cfg):
        """Make an API client for talking with Crane.

        Create an API client for talking to Crane. The client returned by this
        method is similar to the following ``client``:

        >>> client = api.Client(cfg, api.json_handler)

        However:

        * The client's base URL is adjusted as described by :meth:`adjust_url`.
        * The client will send an ``accept:application/json`` header with each
          request.

        :param pulp_smash.config.PulpSmashConfig cfg: Information about a Pulp
            deployment.
        :returns: An API client for talking with Crane.
        :rtype: pulp_smash.api.Client
        """
        client = api.Client(
            cfg,
            api.json_handler,
            {'headers': {'accept': 'application/json'}},
        )
        client.request_kwargs['url'] = SyncPublishMixin.adjust_url(
            client.request_kwargs['url']
        )
        return client


class V1RegistryTestCase(SyncPublishMixin, unittest.TestCase):
    """Create, sync, publish and interact with a v1 Docker registry."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        super().setUpClass()
        cls.cfg = config.get_config()
        cls.repo = {}

    @classmethod
    def tearDownClass(cls):
        """Clean up resources."""
        if cls.repo:
            api.Client(cls.cfg).delete(cls.repo['_href'])
        super().tearDownClass()

    def test_01_set_up(self):
        """Create, sync and publish a repository.

        Specifically, do the following:

        1. Create, sync and publish a Docker repository. Let the repository's
           feed reference a v1 Docker registry.
        2. Make Crane immediately re-read the metadata files published by Pulp.
           (Restart Apache.)
        """
        client = api.Client(self.cfg, api.json_handler)
        body = gen_repo()
        body['importer_config'].update({
            'enable_v1': True,
            'enable_v2': False,
            'feed': DOCKER_V1_FEED_URL,
            'upstream_name': get_upstream_name(self.cfg),
        })
        body['distributors'] = [gen_distributor()]
        type(self).repo = client.post(REPOSITORY_PATH, body)
        type(self).repo = client.get(
            self.repo['_href'],
            params={'details': True}
        )
        utils.sync_repo(self.cfg, self.repo)
        utils.publish_repo(self.cfg, self.repo)

        # Make Crane re-read metadata. (Now!)
        cli.GlobalServiceManager(self.cfg).restart(('httpd',))

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_crane_repositories(self):
        """Issue an HTTP GET request to ``/crane/repositories``.

        Assert that the response is as described by `Crane Admin
        <http://docs.pulpproject.org/plugins/crane/index.html#crane-admin>`_.
        """
        repo_id = self.repo['id']
        repos = self.make_crane_client(self.cfg).get('/crane/repositories')
        self.assertIn(repo_id, repos.keys())
        self.verify_v1_repo(repos[repo_id])

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_crane_repositories_v1(self):  # pylint:disable=invalid-name
        """Issue an HTTP GET request to ``/crane/repositories/v1``.

        Assert that the response is as described by `Crane Admin
        <http://docs.pulpproject.org/plugins/crane/index.html#crane-admin>`_.
        """
        if (self.cfg.version < Version('2.14') or
                selectors.bug_is_untestable(2723, self.cfg.version)):
            self.skipTest('https://pulp.plan.io/issues/2723')
        repo_id = self.repo['id']
        repos = self.make_crane_client(self.cfg).get('/crane/repositories/v1')
        self.assertIn(repo_id, repos.keys())
        self.verify_v1_repo(repos[repo_id])

    def verify_v1_repo(self, repo):
        """Implement the assertions for the ``test_02*`` methods."""
        with self.subTest():
            self.assertFalse(repo['protected'])
        with self.subTest():
            self.assertTrue(repo['image_ids'])
        with self.subTest():
            self.assertTrue(repo['tags'])


class V2RegistryTestCase(SyncPublishMixin, unittest.TestCase):
    """Create, sync, publish and interact with a v2 Docker registry."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        super().setUpClass()
        cls.cfg = config.get_config()
        cls.repo = {}
        for issue_id in (2287, 2384):
            if selectors.bug_is_untestable(issue_id, cls.cfg.version):
                raise unittest.SkipTest(
                    'https://pulp.plan.io/issues/{}'.format(issue_id)
                )

    @classmethod
    def tearDownClass(cls):
        """Clean up resources."""
        if cls.repo:
            api.Client(cls.cfg).delete(cls.repo['_href'])
        super().tearDownClass()

    def test_01_set_up(self):
        """Create, sync and publish a Docker repository.

        Specifically, do the following:

        1. Create, sync and publish a Docker repository. Let the repository's
           feed reference a v2 Docker registry, and let the repository's
           upstream name reference an image with a manifest list.
        2. Make Crane immediately re-read the metadata files published by Pulp.
           (Restart Apache.)
        """
        client = api.Client(self.cfg, api.json_handler)
        body = gen_repo()
        body['importer_config'].update({
            'enable_v1': False,
            'enable_v2': True,
            'feed': DOCKER_V2_FEED_URL,
            'upstream_name': get_upstream_name(self.cfg),
        })
        body['distributors'] = [gen_distributor()]
        type(self).repo = client.post(REPOSITORY_PATH, body)
        type(self).repo = client.get(
            self.repo['_href'],
            params={'details': True}
        )
        utils.sync_repo(self.cfg, self.repo)
        utils.publish_repo(self.cfg, self.repo)

        # Make Crane read the metadata. (Now!)
        cli.GlobalServiceManager(self.cfg).restart(('httpd',))

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_crane_repositories_v2(self):  # pylint:disable=invalid-name
        """Issue an HTTP GET request to ``/crane/repositories/v2``.

        Assert that the response is as described by `Crane Admin
        <http://docs.pulpproject.org/plugins/crane/index.html#crane-admin>`_.
        """
        if (self.cfg.version < Version('2.14') or
                selectors.bug_is_untestable(2723, self.cfg.version)):
            self.skipTest('https://pulp.plan.io/issues/2723')
        repo_id = self.repo['id']
        repos = self.make_crane_client(self.cfg).get('/crane/repositories/v2')
        self.assertIn(repo_id, repos.keys())
        self.assertFalse(repos[repo_id]['protected'])

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_manifest_v1(self):
        """Issue an HTTP GET request to ``/v2/{repo_id}/manifests/latest``.

        Pass each of the followng headers in turn:

        * (none)
        * ``accept:application/json``
        * ``accept:application/vnd.docker.distribution.manifest.v1+json``

        Assert the response matches :data:`MANIFEST_V1`.

        This test targets `Pulp #2336 <https://pulp.plan.io/issues/2336>`_.
        """
        if selectors.bug_is_untestable(2336, self.cfg.version):
            self.skipTest('https://pulp.plan.io/issues/2336')
        client = api.Client(self.cfg, api.json_handler)
        client.request_kwargs['url'] = self.adjust_url(
            client.request_kwargs['url']
        )
        headers_iter = (
            {},
            {'accept': 'application/json'},
            {'accept': 'application/vnd.docker.distribution.manifest.v1+json'},
        )
        for headers in headers_iter:
            with self.subTest(headers=headers):
                manifest = client.get(
                    '/v2/{}/manifests/latest'.format(self.repo['id']),
                    headers=headers,
                )
                validate(manifest, MANIFEST_V1)

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_manifest_v2(self):
        """Issue an HTTP GET request to ``/v2/{repo_id}/manifests/latest``.

        Pass a header of
        ``accept:application/vnd.docker.distribution.manifest.v2+json``. Assert
        that the response body matches :data:`MANIFEST_V2`.

        This test targets `Pulp #2336 <https://pulp.plan.io/issues/2336>`_.
        """
        if selectors.bug_is_untestable(2336, self.cfg.version):
            self.skipTest('https://pulp.plan.io/issues/2336')
        client = api.Client(self.cfg, api.json_handler, {'headers': {
            'accept': 'application/vnd.docker.distribution.manifest.v2+json'
        }})
        client.request_kwargs['url'] = self.adjust_url(
            client.request_kwargs['url']
        )
        manifest = client.get(
            '/v2/{}/manifests/latest'.format(self.repo['id'])
        )
        validate(manifest, MANIFEST_V2)

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_manifest_list(self):
        """Issue an HTTP GET request to ``/v2/{repo_id}/manifests/latest``.

        Pass a header of
        ``accept:application/vnd.docker.distribution.manifest.list.v2+json``
        Assert that:

        * The response body matches :data:`MANIFEST_LIST_V2`.
        * The response has a content-type equal to what was requested.
          (According to Docker's `backward compatiblity` specification, if a
          registry is asked for a manifest list but doesn't have a manifest
          list, it may return a manifest instead. But this test targets
          manifest lists, and it will fail if that happens.)

        .. _backward compatibility:
            https://docs.docker.com/registry/spec/manifest-v2-2/
            #backward-compatibility
        """
        content_type = (
            'application/vnd.docker.distribution.manifest.list.v2+json'
        )
        client = api.Client(
            self.cfg,
            request_kwargs={'headers': {'accept': content_type}}
        )
        client.request_kwargs['url'] = self.adjust_url(
            client.request_kwargs['url']
        )
        response = client.get(
            '/v2/{}/manifests/latest'.format(self.repo['id'])
        )
        self.assertEqual(response.headers['content-type'], content_type)
        validate(response.json(), MANIFEST_LIST_V2)


class NonNamespacedImageTestCase(SyncPublishMixin, unittest.TestCase):
    """Work with an image whose name has no namespace."""

    def test_all(self):
        """Work with an image whose name has no namespace.

        Create, sync and publish a Docker repository whose ``UPSTREAM_NAME``
        doesn't include a namespace. A typical Docker image has a name like
        "library/busybox." When a non-namespaced image name like "busybox" is
        given, a prefix of "library" is assumed.
        """
        cfg = config.get_config()
        client = api.Client(cfg, api.json_handler)
        body = gen_repo()
        body['importer_config'].update({
            'enable_v1': False,
            'enable_v2': True,
            'feed': DOCKER_V2_FEED_URL,
            'upstream_name': 'busybox',
        })
        body['distributors'] = [gen_distributor()]
        repo = client.post(REPOSITORY_PATH, body)
        self.addCleanup(client.delete, repo['_href'])
        repo = client.get(repo['_href'], params={'details': True})
        utils.sync_repo(cfg, repo)
        utils.publish_repo(cfg, repo)

        # Make Crane read the metadata. (Now!)
        cli.GlobalServiceManager(cfg).restart(('httpd',))

        # Get and inspect /crane/repositories/v2.
        if (cfg.version >= Version('2.14') and
                selectors.bug_is_testable(2723, cfg.version)):
            client = self.make_crane_client(cfg)
            repo_id = repo['id']
            repos = client.get('/crane/repositories/v2')
            self.assertIn(repo_id, repos.keys())
            self.assertFalse(repos[repo_id]['protected'])


class NoAmd64LinuxTestCase(SyncPublishMixin, unittest.TestCase):
    """Sync a Docker image with no amd64/linux build.

    A manifest list lets a single Docker repository contain multiple images.
    This is useful in the case where an image contains platform-specific code,
    and an image must be built for each each supported architecture, OS, etc.

    When a modern Docker client fetches an image, it does the following:

    1. Get a manifest list.
    2. Look through the list of available images.
    3. Pick out an image that functions on the current host's platform.
    4. Get a manifest for that image.
    5. Use the information in the manifest to get the image layers.

    Older Docker clients aren't aware of manifest lists, and when they go to
    fetch an image, they just ask for any old manifest from a repository. When
    a Docker registry receives such a request, it does the following:

    1. Look through the list of available images.
    2. If an image with an ``architecture`` of ``amd64`` and an ``os`` of
       ``linux`` is available, return its manifest. Otherwise, return an HTTP
       404.

    This test case verifies Pulp's behaviour in the case where an upstream
    Docker repository has content described by a manifest list.

    This test case doesn't verify Pulp's behaviour in the case where an
    upstream Docker repository has content described by a v2 manifest or v1
    manifest. In these cases, the correct behaviour of a Docker registry is not
    well defined. See the `backward compatibility`_ documentation.

    .. _backward compatibility:
        https://docs.docker.com/registry/spec/manifest-v2-2/#backward-compatibility
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        super().setUpClass()
        cls.cfg = config.get_config()
        cls.repo = {}
        if selectors.bug_is_untestable(2384, cls.cfg.version):
            raise unittest.SkipTest('https://pulp.plan.io/issues/2384')

    @classmethod
    def tearDownClass(cls):
        """Clean up resources."""
        if cls.repo:
            api.Client(cls.cfg).delete(cls.repo['_href'])
        super().tearDownClass()

    def test_01_set_up(self):
        """Create, sync and publish a Docker repository.

        Specifically, do the following:

        1. Create, sync and publish a Docker repository. Let the repository's
           upstream name reference a repository that has an image with a
           manifest list and no amd64/linux build.
        2. Make Crane immediately re-read the metadata files published by Pulp.
           (Restart Apache.)
        """
        client = api.Client(self.cfg, api.json_handler)
        body = gen_repo()
        body['importer_config'].update({
            'enable_v1': False,
            'enable_v2': True,
            'feed': DOCKER_V2_FEED_URL,
            # DOCKER_UPSTREAM_NAME (dmage/manifest-list-test) has an image
            # without any amd64/linux build. However, it has a v1 manifest.
            'upstream_name': 'dmage/busybox',
        })
        body['distributors'] = [gen_distributor()]
        type(self).repo = client.post(REPOSITORY_PATH, body)
        type(self).repo = client.get(
            self.repo['_href'],
            params={'details': True}
        )
        utils.sync_repo(self.cfg, self.repo)
        utils.publish_repo(self.cfg, self.repo)

        # Make Crane read metadata. (Now!)
        cli.GlobalServiceManager(self.cfg).restart(('httpd',))

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_manifest_list(self):
        """Get a manifest list.

        Assert that:

        * The response headers include a content-type of
          ``accept:application/vnd.docker.distribution.manifest.list.v2+json``.
          (See :meth:`test_02_get_manifest_list`.
        * The response body matches :data:`MANIFEST_LIST_V2`.
        * The returned manifest list doesn't include any entry where
          ``architecture`` of ``amd64`` and ``os`` is ``linux``.
        """
        # get a manifest list
        content_type = (
            'application/vnd.docker.distribution.manifest.list.v2+json'
        )
        client = api.Client(self.cfg, request_kwargs={
            'headers': {'accept': content_type}
        })
        client.request_kwargs['url'] = self.adjust_url(
            client.request_kwargs['url']
        )
        response = client.get(
            '/v2/{}/manifests/fake-arm-only'.format(self.repo['id'])
        )

        # perform assertions
        self.assertEqual(
            response.headers['content-type'],
            content_type,
            response.headers
        )
        manifest_list = response.json()
        validate(manifest_list, MANIFEST_LIST_V2)
        for manifest in manifest_list['manifests']:
            self.assertFalse(
                manifest['platform'].get('architecture') == 'amd64' and
                manifest['platform'].get('os') == 'linux',
                manifest_list
            )

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_manifest_v2(self):
        """Get a v2 manifest. Assert that an HTTP 404 is returned."""
        client = api.Client(self.cfg, api.echo_handler, {'headers': {
            'accept': 'application/vnd.docker.distribution.manifest.v2+json'
        }})
        client.request_kwargs['url'] = self.adjust_url(
            client.request_kwargs['url']
        )
        response = client.get(
            '/v2/{}/manifests/fake-arm-only'.format(self.repo['id'])
        )
        self.assertEqual(response.status_code, 404, response.content)

    @selectors.skip_if(bool, 'repo', False)
    def test_02_get_manifest_v1(self):
        """Get a v1 manifest. Assert that an HTTP 404 is returned."""
        client = api.Client(self.cfg, api.echo_handler, {'headers': {
            'accept': 'application/vnd.docker.distribution.manifest.v1+json'
        }})
        client.request_kwargs['url'] = self.adjust_url(
            client.request_kwargs['url']
        )
        response = client.get(
            '/v2/{}/manifests/fake-arm-only'.format(self.repo['id'])
        )
        self.assertEqual(response.status_code, 404, response.content)


class RepoRegistryIdTestCase(SyncPublishMixin, unittest.TestCase):
    """Show Pulp can publish repos with varying ``repo_registry_id`` values."""

    def test_all(self):
        """Show Pulp can publish repos with varying ``repo_registry_id`` values.

        The ``repo_registry_id`` setting defines a Docker repository's name as
        seen by clients such as the Docker CLI. It's traditionally a two-part
        name such as ``docker/busybox``, but according to `Pulp #2368`_, it can
        contain an arbitrary number of slashes. This test case verifies that
        the ``repo_registry_id`` can be set to values containing one, two and
        three slashes.

        Also see: `Pulp #2723`_.

        .. _Pulp #2368: https://pulp.plan.io/issues/2368
        .. _Pulp #2723: https://pulp.plan.io/issues/2723
        """
        cfg = config.get_config()
        if (cfg.version < Version('2.14') or
                selectors.bug_is_untestable(2723, cfg.version)):
            self.skipTest('https://pulp.plan.io/issues/2723')
        for i in range(1, 4):
            repo_registry_id = '/'.join(utils.uuid4() for _ in range(i))
            with self.subTest(repo_registry_id=repo_registry_id):
                self.do_test(cfg, repo_registry_id)

    def do_test(self, cfg, repo_registry_id):
        """Execute the test with the given ``repo_registry_id``."""
        # Create, sync and publish.
        client = api.Client(cfg, api.json_handler)
        body = gen_repo()
        body['importer_config'].update({
            'enable_v1': False,
            'enable_v2': True,
            'feed': DOCKER_V2_FEED_URL,
            'upstream_name': get_upstream_name(cfg),
        })
        body['distributors'] = [gen_distributor()]
        body['distributors'][0]['distributor_config']['repo-registry-id'] = (
            repo_registry_id
        )
        repo = client.post(REPOSITORY_PATH, body)
        self.addCleanup(client.delete, repo['_href'])
        repo = client.get(repo['_href'], params={'details': True})
        utils.sync_repo(cfg, repo)
        utils.publish_repo(cfg, repo)
        cli.GlobalServiceManager(cfg).restart(('httpd',))  # restart Crane

        # Get and inspect /crane/repositories/v2.
        client = self.make_crane_client(cfg)
        repos = client.get('/crane/repositories/v2')
        self.assertIn(repo_registry_id, repos.keys())
        self.assertFalse(repos[repo_registry_id]['protected'])
