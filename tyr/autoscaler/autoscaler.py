from boto.ec2.autoscale import AutoScaleConnection
from boto.ec2.autoscale import LaunchConfiguration
from boto.ec2.autoscale import AutoScalingGroup
import boto.ec2
import logging


class AutoScaler(object):
    '''
    Autoscaler setup class
    '''

    log = logging.getLogger('Clusters.AutoScaler')
    log.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S')
    ch.setFormatter(formatter)
    log.addHandler(ch)

    def __init__(self, launch_configuration,
                 autoscaling_group,
                 node_obj,
                 desired_capacity=1,
                 max_size=1,
                 min_size=1,
                 default_cooldown=300,
                 availability_zones=None,
                 subnet_ids=None,
                 health_check_grace_period=300,
                 enable_classiclink=False):

        self.launch_configuration = launch_configuration
        self.autoscaling_group = autoscaling_group
        self.desired_capacity = desired_capacity

        # You can set a list of availability zones explicitly, else it will
        # just use the one from the node object
        if availability_zones:
            self.autoscale_availability_zones = availability_zones
        else:
            self.autoscale_availability_zones = [node_obj.availability_zone]

        # If you set these they must match the availability zones
        if subnet_ids:
            self.autoscale_subnets = subnet_ids
        else:
            self.autoscale_subnets = [node_obj.subnet_id]

        self.availability_zones = availability_zones
        self.node_obj = node_obj
        self.max_size = max_size
        self.min_size = min_size
        self.default_cooldown = default_cooldown
        self.health_check_grace_period = health_check_grace_period
        self.enable_classiclink = enable_classiclink

        if self.enable_classiclink:
            self.vpc_security_groups = self.node_obj.get_security_group_ids(
                self.node_obj.classic_link_vpc_security_groups)
            self.classiclink_vpc_id = node_obj.subnet_id
        else:
            self.vpc_security_groups = None
            self.classiclink_vpc_id = None

    def establish_autoscale_connection(self):
        try:
            self.conn = boto.ec2.autoscale.connect_to_region(self.node_obj.region)
            self.log.info('Established connection to autoscale')
        except:
            raise

    def create_launch_configuration(self):
        self.log.info("Getting launch_configuration: {0}"
            .format(self.launch_configuration))

        lc = self.conn.get_all_launch_configurations(
            names=[self.launch_configuration])
        if not lc:
            self.log.info("Creating new launch_configuration: {0}"
                          .format(self.launch_configuration))
            lc = LaunchConfiguration(name=self.launch_configuration,
                                     image_id=self.node_obj.ami,
                                     key_name=self.node_obj.keypair,
                                     security_groups=self.node_obj.get_security_group_ids(
                                         self.node_obj.security_groups),
                                     classic_link_vpc_security_groups=self.vpc_security_groups,
                                     classic_link_vpc_id=self.classiclink_vpc_id,
                                     user_data=self.node_obj.user_data,
                                     instance_profile_name=self.node_obj.role)
            self.conn.create_launch_configuration(lc)
            self.launch_configuration = lc

    def create_autoscaling_group(self):
        existing_asg = self.conn.get_all_groups(
            names=[self.autoscaling_group])

        if not existing_asg:
            self.log.info("Creating new autoscaling group: {0}"
                          .format(self.autoscaling_group))

            ag = AutoScalingGroup(name=self.autoscaling_group,
                                  availability_zones=self.autoscale_availability_zones,
                                  desired_capacity=self.desired_capacity,
                                  health_check_period=self.health_check_grace_period,
                                  launch_config=self.launch_configuration,
                                  min_size=self.min_size,
                                  max_size=self.max_size,
                                  default_cooldown=self.default_cooldown,
                                  vpc_zone_identifier=self.autoscale_subnets,
                                  connection=self.conn)
            self.conn.create_auto_scaling_group(ag)
        else:
            self.log.info('Autoscaling group {0} already exists.'
                          .format(self.autoscaling_group))

    def autorun(self):
        self.establish_autoscale_connection()
        self.create_launch_configuration()
        self.create_autoscaling_group()
