import logging
from tyr.servers.iis import IISNode
from tyr.clusters.autoscaling import AutoScaler


class IISCluster():

    def __init__(self, group=None,
                 server_type=None,
                 instance_type=None,
                 environment=None,
                 ami=None,
                 region=None,
                 tags=None,
                 root_volume_size=40,
                 subnet_ids=[],
                 role=None,
                 keypair=None,
                 security_groups=None,
                 autoscaling_group=None,
                 desired_capacity=1,
                 max_size=1,
                 min_size=1,
                 default_cooldown=300,
                 availability_zones=None,
                 health_check_grace_period=300,
                 launch_configuration=None):

        self.log = logging.getLogger('Tyr.Clusters.IISCluster')
        self.group = group
        self.server_type = server_type
        self.instance_type = instance_type
        self.environment = environment
        self.ami = ami
        self.region = region
        self.role = role
        self.tags = tags
        self.root_volume_size = root_volume_size
        self.subnet_ids = subnet_ids

        self.keypair = keypair
        self.security_groups = security_groups
        self.autoscaling_group = autoscaling_group
        self.desired_capacity = desired_capacity
        self.max_size = max_size
        self.min_size = min_size
        self.default_cooldown = default_cooldown
        self.availability_zones = availability_zones
        self.health_check_grace_period = health_check_grace_period
        self.launch_configuration = launch_configuration

        if subnet_ids:
            self.node_subnet = self.subnet_ids[0]
        else:
            self.node_subnet = None

        if self.availability_zones:
            self.node_zone = availability_zones[0]
        else:
            self.node_zone = None

        if not self.launch_configuration:
            self.launch_configuration = "{env}-{grp}-web".format(
                env=self.environment[0], grp=self.group)
        if not self.autoscaling_group:
            if self.subnet_ids:
                templ = "{env}-{grp}-web-asg-vpc"
            else:
                templ = "{env}-{grp}-web-asg"
            self.autoscaling_group = templ.format(
                env=self.environment[0], grp=self.group)

        # Template to use with an autoscaling group
        self.node = IISNode(group=self.group,
                            server_type=self.server_type,
                            instance_type=self.instance_type,
                            environment=self.environment,
                            ami=self.ami,
                            region=self.region,
                            role=self.role,
                            keypair=self.keypair,
                            availability_zone=self.node_zone,
                            security_groups=self.security_groups,
                            subnet_id=self.node_subnet)

        self.autoscaler = AutoScaler(launch_configuration=self.launch_configuration,
                                     autoscaling_group=self.autoscaling_group,
                                     desired_capacity=self.desired_capacity,
                                     tags=self.tags,
                                     root_volume_size=self.root_volume_size,
                                     max_size=self.max_size,
                                     min_size=self.min_size,
                                     default_cooldown=self.default_cooldown,
                                     availability_zones=self.availability_zones,
                                     subnet_ids=self.subnet_ids,
                                     health_check_grace_period=self.
                                     health_check_grace_period,
                                     node_obj=self.node)

    def provision(self):
        self.log.info('Provisioning IISCluster')
        self.node.configure()

        self.log.info('Creating autoscaler')
        self.autoscaler.autorun()

    def baked(self):
        return False

    def autorun(self):
        self.provision()
