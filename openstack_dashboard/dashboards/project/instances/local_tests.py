# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from openstack_dashboard.test.helpers import TestCase
from openstack_dashboard.dashboards.project.instances.tests import *
from openstack_dashboard.test.local.test_data import utils as test_utils

try:
    from openstack_dashboard.test.local.settings import *  # noqa
    logging.info('Importing local settings')
except ImportError:
    logging.warning("No local_settings file found.")
    raise('Create openstack_dashboard/test/local/settings.py')


class LocalInstanceTests(InstanceTests):
    def setUp(self):
        super(LocalInstanceTests,self).setUp()

    def _setup_local_test_data(self):
       super(TestCase,self)._setup_test_data()
       test_utils.load_test_data(self)
       self.context = {'authorized_tenants': self.tenants.list()}

    def _setup_test_data(self):
        self._setup_local_test_data()
        
    @helpers.create_stubs({api.nova: ('extension_supported',
                                      'flavor_list',
                                      'keypair_list',
                                      'server_group_list',
                                      'tenant_absolute_limits',
                                      'availability_zone_list',),
                           api.network: ('security_group_list',),
                           cinder: ('volume_snapshot_list',
                                    'volume_list',),
                           api.neutron: ('network_list',
                                         'profile_list',
                                         'port_list'),
                           api.glance: ('image_list_detailed',)})

    def test_launch_instance_get(self,
                                 expect_password_fields=True,
                                 block_device_mapping_v2=True,
                                 custom_flavor_sort=None,
                                 only_one_network=False,
                                 disk_config=True,
                                 config_drive=True,
                                 config_drive_default=False,
                                 test_with_profile=False):
        image = self.images.first()

        api.nova.extension_supported('BlockDeviceMappingV2Boot',
                                     IsA(http.HttpRequest)) \
            .AndReturn(block_device_mapping_v2)
        cinder.volume_list(IsA(http.HttpRequest),
                           search_opts=VOLUME_SEARCH_OPTS) \
            .AndReturn([])
        cinder.volume_snapshot_list(IsA(http.HttpRequest),
                                    search_opts=SNAPSHOT_SEARCH_OPTS) \
            .AndReturn([])
        api.glance.image_list_detailed(
            IsA(http.HttpRequest),
            filters={'is_public': True, 'status': 'active'}) \
            .AndReturn([self.images.list(), False, False])
        api.glance.image_list_detailed(
            IsA(http.HttpRequest),
            filters={'property-owner_id': self.tenant.id,
                     'status': 'active'}) \
            .AndReturn([[], False, False])
        api.neutron.network_list(IsA(http.HttpRequest),
                                 tenant_id=self.tenant.id,
                                 shared=False) \
            .AndReturn(self.networks.list()[:1])
        if only_one_network:
            api.neutron.network_list(IsA(http.HttpRequest),
                                     shared=True).AndReturn([])
        else:
            api.neutron.network_list(IsA(http.HttpRequest),
                                     shared=True) \
                .AndReturn(self.networks.list()[1:])

        api.neutron.network_list(IsA(http.HttpRequest),
                                 tenant_id=self.tenant.id,
                                 shared=False) \
            .AndReturn(self.networks.list()[:1])
        api.neutron.network_list(IsA(http.HttpRequest),
                                 shared=True) \
            .AndReturn(self.networks.list()[1:])
        for net in self.networks.list():
            api.neutron.port_list(IsA(http.HttpRequest),
                                  network_id=net.id) \
                .AndReturn(self.ports.list())

        if test_with_profile:
            policy_profiles = self.policy_profiles.list()
            api.neutron.profile_list(IsA(http.HttpRequest),
                                     'policy').AndReturn(policy_profiles)
        api.nova.extension_supported('DiskConfig',
                                     IsA(http.HttpRequest)) \
            .AndReturn(disk_config)
        api.nova.extension_supported(
            'ConfigDrive', IsA(http.HttpRequest)).AndReturn(config_drive)
        api.nova.extension_supported(
            'ServerGroups', IsA(http.HttpRequest)).AndReturn(True)
        api.nova.server_group_list(IsA(http.HttpRequest)) \
            .AndReturn(self.server_groups.list())
        api.nova.tenant_absolute_limits(IsA(http.HttpRequest), reserved=True)\
            .AndReturn(self.limits['absolute'])
        api.nova.flavor_list(IsA(http.HttpRequest)) \
            .AndReturn(self.flavors.list())
        api.nova.flavor_list(IsA(http.HttpRequest)) \
            .AndReturn(self.flavors.list())
        api.nova.keypair_list(IsA(http.HttpRequest)) \
            .AndReturn(self.keypairs.list())
        api.network.security_group_list(IsA(http.HttpRequest)) \
            .AndReturn(self.security_groups.list())
        api.nova.availability_zone_list(IsA(http.HttpRequest)) \
            .AndReturn(self.availability_zones.list())

        self.mox.ReplayAll()

        url = reverse('horizon:project:instances:launch')
        params = urlencode({"source_type": "image_id",
                            "source_id": image.id})
        res = self.client.get("%s?%s" % (url, params))

        workflow = res.context['workflow']
        self.assertTemplateUsed(res, views.WorkflowView.template_name)
        self.assertEqual(res.context['workflow'].name,
                         workflows.LaunchInstance.name)
        step = workflow.get_step("setinstancedetailsaction")
        self.assertEqual(step.action.initial['image_id'], image.id)
        self.assertQuerysetEqual(
            workflow.steps,
            ['<SetInstanceDetails: setinstancedetailsaction>',
             '<SetAccessControls: setaccesscontrolsaction>',
             '<SetNetwork: setnetworkaction>',
             '<SetNetworkPorts: setnetworkportsaction>',
             '<PostCreationStep: customizeaction>',
             '<SetAdvanced: setadvancedaction>'])

        if custom_flavor_sort == 'id':
            # Reverse sorted by id
            sorted_flavors = (
                ('hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh', 'nondurable1.massive'),
                ('gggggggg-gggg-gggg-gggg-gggggggggggg', 'e1.massive'),
                ('ffffffff-ffff-ffff-ffff-ffffffffffff', 'generic1.tiny'),
                ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'm1.metadata'),
                ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'm1.secret'),
                ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'm1.massive'),
                ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'm1.tiny'),
            )
        elif custom_flavor_sort == 'name':
            sorted_flavors = (
                ('gggggggg-gggg-gggg-gggg-gggggggggggg', 'e1.massive'),
                ('ffffffff-ffff-ffff-ffff-ffffffffffff', 'generic1.tiny'),
                ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'm1.massive'),
                ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'm1.metadata'),
                ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'm1.secret'),
                ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'm1.tiny'),
                ('hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh', 'nondurable1.massive'),
            )
        elif custom_flavor_sort == CREATE_INSTANCE_FLAVOR_SORT['key']:
            sorted_flavors = (
                ('ffffffff-ffff-ffff-ffff-ffffffffffff', 'generic1.tiny'), #(0,512)
                ('hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh', 'nondurable1.massive'), #(1,10000)
                ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'm1.tiny'), #(2,512)
                ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'm1.massive'), #(2,10000)
                ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'm1.secret'), #(2,10000)
                ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'm1.metadata'), #(2,10000)
                ('gggggggg-gggg-gggg-gggg-gggggggggggg', 'e1.massive'), #(3,10000)
            )
        elif custom_flavor_sort == helpers.my_custom_sort:
            sorted_flavors = (
                ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'm1.secret'),
                ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'm1.tiny'),
                ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'm1.massive'),
                ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'm1.metadata'),
                ('ffffffff-ffff-ffff-ffff-ffffffffffff', 'generic1.tiny'),
                ('gggggggg-gggg-gggg-gggg-gggggggggggg', 'e1.massive'),
                ('hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh', 'nondurable1.massive'),
            )
        else:
            # Default - sorted by RAM
            sorted_flavors = (
                ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'm1.tiny'),
                ('ffffffff-ffff-ffff-ffff-ffffffffffff', 'generic1.tiny'),
                ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'm1.massive'),
                ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'm1.secret'),
                ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'm1.metadata'),
                ('gggggggg-gggg-gggg-gggg-gggggggggggg', 'e1.massive'),
                ('hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh', 'nondurable1.massive'),
            )

        select_options = ''.join([
            '<option value="%s">%s</option>' % (f[0], f[1])
            for f in sorted_flavors
        ])
        self.assertContains(res, select_options)

        password_field_label = 'Admin Pass'
        if expect_password_fields:
            self.assertContains(res, password_field_label)
        else:
            self.assertNotContains(res, password_field_label)

        boot_from_image_field_label = 'Boot from image (creates a new volume)'
        if block_device_mapping_v2:
            self.assertContains(res, boot_from_image_field_label)
        else:
            self.assertNotContains(res, boot_from_image_field_label)

        checked_box = '<input checked="checked" id="id_network_0"'
        if only_one_network:
            self.assertContains(res, checked_box)
        else:
            self.assertNotContains(res, checked_box)

        disk_config_field_label = 'Disk Partition'
        if disk_config:
            self.assertContains(res, disk_config_field_label)
        else:
            self.assertNotContains(res, disk_config_field_label)

        config_drive_field_label = 'Configuration Drive'
        if config_drive:
            self.assertContains(res, config_drive_field_label)
        else:
            self.assertNotContains(res, config_drive_field_label)

        step = workflow.get_step("setadvancedaction")
        self.assertEqual(step.action.initial['config_drive'],
                         config_drive_default)


    @django.test.utils.override_settings(
        CREATE_INSTANCE_FLAVOR_SORT=CREATE_INSTANCE_FLAVOR_SORT
    )
    def test_launch_instance_get_custom_flavor_sort_by_callable(self):
        self.test_launch_instance_get(
            custom_flavor_sort=CREATE_INSTANCE_FLAVOR_SORT['key'])
