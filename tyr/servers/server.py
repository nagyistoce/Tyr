from exceptions import *
import boto.ec2
import boto.route53
import logging
import os.path
import chef
import time
import json
import re
import urllib
from paramiko.client import AutoAddPolicy, SSHClient
from tyr.policies import policies
from tyr.security_groups import security_groups

class Server(object):

    NAME_TEMPLATE='{envcl}-{zone}-{index}'
    NAME_SEARCH_PREFIX='{envcl}-{zone}-'
    NAME_AUTO_INDEX=True

    IAM_ROLE_POLICIES = []

    CHEF_RUNLIST=['role[RoleBase]']

    def __init__(self, group=None, server_type=None, instance_type=None,
                    environment=None, ami=None, region=None, role=None,
                    keypair=None, availability_zone=None, security_groups=None,
                    block_devices=None, chef_path=None):

        self.instance_type = instance_type
        self.group = group
        self.server_type= server_type
        self.environment = environment
        self.ami = ami
        self.region = region
        self.role = role
        self.keypair = keypair
        self.availability_zone = availability_zone
        self.security_groups = security_groups
        self.block_devices = block_devices
        self.chef_path = chef_path

    def establish_logger(self):

        try:
            return self.log
        except:
            pass

        log = logging.getLogger(self.__class__.__name__)

        if not log.handlers:
            log.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                    '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
                    datefmt='%H:%M:%S')
            ch.setFormatter(formatter)
            log.addHandler(ch)

        self.log = log

    def configure(self):

        if self.instance_type is None:
            self.log.warn('No Instance Type provided')
            self.instance_type = 'm3.medium'

        self.log.info('Using Instance Type "{instance_type}"'.format(
                                            instance_type = self.instance_type))

        if self.group is None:
            self.log.warn('No group provided')
            raise InvalidCluster('A group must be specified.')

        self.log.info('Using group "{group}"'.format(
                        group = self.group))

        if self.server_type is None:
            self.log.warn('No type provided')
            raise InvalidCluster('A type must be specified.')

        self.log.info('Using type "{server_type}"'.format(
                        server_type = self.server_type))


        if self.environment is None:
            self.log.warn('No environment provided')
            self.environment = 'test'

        self.environment = self.environment.lower()

        self.log.info('Using Environment "{environment}"'.format(
                        environment = self.environment))

        if self.region is None:
            self.log.warn('No region provided')
            self.region = 'us-east-1'

        valid = lambda r: r in [region.name for region in boto.ec2.regions()]

        if not valid(self.region):

            error = '"{region}" is not a valid EC2 region'.format(
                        region=self.region)
            raise RegionDoesNotExist(error)

        self.log.info('Using EC2 Region "{region}"'.format(
                        region = self.region))

        self.establish_ec2_connection()
        self.establish_iam_connection()
        self.establish_route53_connection()

        if self.ami is None:
            self.log.warn('No AMI provided')
            self.ami = 'ami-146e2a7c'

        try:
            self.ec2.get_all_images(image_ids=[self.ami])
        except Exception, e:
            self.log.error(str(e))
            if 'Invalid id' in str(e):
                error = '"{ami}" is not a valid AMI'.format(ami = self.ami)
                raise InvalidAMI(error)

        self.log.info('Using EC2 AMI "{ami}"'.format(ami = self.ami))

        if self.role is None:
            self.log.warn('No IAM Role provided')
            self.role = self.envcl

        self.log.info('Using IAM Role "{role}"'.format(role = self.role))

        self.resolve_iam_role()

        if self.keypair is None:
            self.log.warn('No EC2 Keypair provided')
            self.keypair = 'stage-key'
            if self.environment == 'prod':
                self.keypair = 'bkaiserkey'

        valid = lambda k: k in [pair.name for pair in
                self.ec2.get_all_key_pairs()]

        if not valid(self.keypair):
            error = '"{keypair}" is not a valid EC2 keypair'.format(
                        keypair = self.keypair)
            raise InvalidKeyPair(error)

        self.log.info('Using EC2 Key Pair "{keypair}"'.format(
                        keypair = self.keypair))

        if self.availability_zone is None:
            self.log.warn('No EC2 availability zone provided')
            self.availability_zone = 'c'

        if len(self.availability_zone) == 1:
            self.availability_zone = self.region+self.availability_zone

        valid = lambda z: z in [zone.name for zone in self.ec2.get_all_zones()]

        if not valid(self.availability_zone):
            error = '"{zone}" is not a valid EC2 availability zone'.format(
                    zone = self.availability_zone)
            raise InvalidAvailabilityZone(error)

        self.log.info('Using EC2 Availability Zone "{zone}"'.format(
                        zone = self.availability_zone))

        if self.security_groups is None:
            self.log.warn('No EC2 security groups provided')

            self.security_groups = ['management', 'chef-nodes']
            self.security_groups.append(self.envcl)

        self.log.info('Using security groups {groups}'.format(
                        groups=', '.join(self.security_groups)))

        self.resolve_security_groups()

        if self.block_devices is None:
            self.log.warn('No block devices provided')

            self.block_devices = [{
                                    'type': 'ephemeral',
                                    'name': 'ephemeral0',
                                    'path': 'xvdc'
                                  }]

        self.log.info('Using EC2 block devices {devices}'.format(
                        devices = self.block_devices))

        if self.chef_path is None:
            self.log.warn('No Chef path provided')
            self.chef_path = '~/.chef'

        self.chef_path = os.path.expanduser(self.chef_path)

        self.log.info('Using Chef path "{path}"'.format(
                                path = self.chef_path))



    def next_index(self, supplemental={}):

        try:
            return self.index
        except Exception:
            pass

        template = self.NAME_SEARCH_PREFIX+'*'

        name_filter = template.format(**supplemental)

        filters = {
            'tag:Name': name_filter,
            'instance-state-name': 'running'
        }

        reservations = self.ec2.get_all_instances(filters=filters)

        instances = []

        for reservation in reservations:
            instances.extend(reservation.instances)

        names = [instance.tags['Name'] for instance in instances]

        indexes = [name.split('-')[-1] for name in names]
        indexes = [int(index) for index in indexes if index.isdigit()]

        index = -1

        for i in range(99):
            if (i+1) not in indexes:
                index = i+1
                break

        self.index = str(index)

        if len(self.index) == 1:
            self.index = '0'+self.index

        return self.index

    @property
    def envcl(self):

        template = '{environment}-{group}-{server_type}'
        envcl = template.format(environment = self.environment[0],
                                  group = self.group,
                                  server_type = self.server_type)

        self.log.info('Using envcl {envcl}'.format(envcl = envcl))

        return envcl

    @property
    def name(self):

        try:
            return self.unique_name
        except Exception:
            pass

        template = self.NAME_TEMPLATE

        supplemental = self.__dict__.copy()

        supplemental['zone'] = self.availability_zone[-1:]
        supplemental['envcl'] = self.envcl

        if self.NAME_AUTO_INDEX:

            index = self.next_index(supplemental)
            supplemental['index'] = index

        self.unique_name = template.format(**supplemental)

        self.log.info('Using node name {name}'.format(name = self.unique_name))

        return self.unique_name

    @property
    def hostname(self):

        template = '{name}.thorhudl.com'

        if self.environment == 'stage':
            template = '{name}.app.staghudl.com'
        elif self.environment == 'prod':
            template = '{name}.app.hudl.com'

        hostname = template.format(name = self.name)

        self.log.info('Using hostname {hostname}'.format(hostname = hostname))

        return hostname

    @property
    def user_data(self):

        template = """#!/bin/bash
sed -i '/requiretty/d' /etc/sudoers
hostname {hostname}
echo '127.0.0.1 {fqdn} {hostname}' > /etc/hosts
mkdir /etc/chef
touch /etc/chef/client.rb
echo '{validation_key}' > /etc/chef/validation.pem
echo 'chef_server_url "http://chef.app.hudl.com/"
node_name "{name}"
validation_client_name "chef-validator"' > /etc/chef/client.rb
curl -L https://www.opscode.com/chef/install.sh | bash;
yum install -y gcc
chef-client -S 'http://chef.app.hudl.com/' -N {name} -L {logfile}"""

        validation_key_path = os.path.expanduser('~/.chef/chef-validator.pem')
        validation_key_file = open(validation_key_path, 'r')
        validation_key = validation_key_file.read()

        return template.format(hostname = self.hostname,
                                fqdn = self.hostname,
                                validation_key = validation_key,
                                name = self.name,
                                logfile = '/var/log/chef-client.log')

    @property
    def tags(self):

        tags = {}
        tags['Name'] = self.name
        tags['Environment'] = self.environment
        tags['Group'] = self.group
        tags['Role'] = 'Role'+self.server_type.capitalize()

        self.log.info('Using instance tags {tags}'.format(tags = tags))

        return tags

    @property
    def blockdevicemapping(self):

        bdm = boto.ec2.blockdevicemapping.BlockDeviceMapping()

        self.log.info('Created new Block Device Mapping')

        for d in self.block_devices:

            device = boto.ec2.blockdevicemapping.BlockDeviceType()

            if 'size' in d.keys():
                device.size = d['size']

            if d['type'] == 'ephemeral':
                device.ephemeral_name = d['name']

            bdm['/dev/'+d['path']] = device

            if d['type'] == 'ephemeral':
                if 'size' in d.keys():
                    self.log.info("""Created new ephemeral device at {path}
named {name} of size {size}""".format(path = d['path'], name = d['name'],
                                        size = d['size']))
                else:
                    self.log.info("""Created new ephemeral device at {path}
named {name}""".format(path = d['path'], name = d['name']))

            else:
                self.log.info("""Created new EBS device at {path} of size
{size}""".format(path = d['path'], size = d['size']))

        return bdm

    def resolve_security_groups(self):

        exists = lambda s: s in [group.name for group in
                self.ec2.get_all_security_groups()]

        for group in self.security_groups:
            if not exists(group):
                self.log.info('Security Group {group} does not exist'.format(
                                group = group))
                self.ec2.create_security_group(group, group)
                self.log.info('Created security group {group}'.format(
                                group = group))
            else:
                self.log.info('Security Group {group} already exists'.format(
                                group = group))

        for group in self.security_groups:
            for key in security_groups.keys():
                if not re.match(key, group): continue

                self.log.info('Setting inbound rules for {group}'.format(
                                                            group = group))

                g = self.ec2.get_all_security_groups(groupnames=[group])[0]

                for rule in security_groups[key]['rules']:

                    self.log.info('Adding rule {rule}'.format(rule=rule))

                    params = {}

                    try:
                        params['ip_protocol'] = rule['ip_protocol']
                    except KeyError:
                        self.log.warning('No IP protocol defined. Using TCP.')
                        params['ip_protocol'] = 'tcp'

                    if isinstance(rule['port'], (int, long)):
                        params['from_port'] = rule['port']
                        params['to_port'] = rule['port']
                    elif '-' in rule['port']:
                        ports = [int(p) for p in rule['port'].split('-')]

                        if ports[0] == ports[1]:
                            params['from_port'] = ports[0]
                            params['to_port'] = ports[0]
                        else:
                            params['from_port'] = min(ports)
                            params['to_port'] = max(ports)
                    else:
                        params['from_port'] = int(rule['port'])
                        params['to_port'] = int(rule['port'])

                    cidr_ip_pattern = '^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.)' \
                    '{3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)/(3[0-2]|[1-2]?[0-9])$'

                    ip_pattern = '^(\[0-9]{1,3})\.(\[0-9]{1,3})\.(\[0-9]{1,3}' \
                    ')\.(\[0-9]{1,3})$'

                    complete_rules = []

                    if isinstance(rule['source'], str):
                        rule['source'] = [rule['source']]

                    for source in rule['source']:
                        complete_params = params.copy()

                        if isinstance(source, str):
                            source = {
                                        'value': source,
                                        'rule': '.*'
                                     }

                        if not re.match(source['rule'], group): continue

                        if re.match(cidr_ip_pattern, source['value']):
                            complete_params['cidr_ip'] = source['value']
                        elif re.match(ip_pattern, source['value']):
                            complete_params['cidr_ip'] = source['value']+'/32'
                        else:
                            name = source['value'].format(
                                                        env=self.environment[0],
                                                        group=self.group,
                                                        type_=self.server_type)

                            groups = self.ec2.get_all_security_groups(
                                                            groupnames=[name])

                            complete_params['src_group'] = groups[0]

                        complete_rules.append(complete_params)

                    for complete_params in complete_rules:
                        self.log.info('Adding inbound rule {rule}'.format(
                                                        rule=complete_params))
                        try:
                            g.authorize(**complete_params)
                            self.log.info('Added inbound rule')
                        except Exception, e:
                            self.log.warn('Failed to add inbound rule')
                            if 'InvalidPermission.Duplicate' in str(e):
                                self.log.info('Inbound rule already exists')
                            else:
                                raise e

    def resolve_iam_role(self):

        role_exists = False
        profile_exists = False

        try:
            profile = self.iam.get_instance_profile(self.role)
            profile_exists = True
        except Exception, e:
            if '404 Not Found' in str(e):
                pass
            else:
                self.log.error(str(e))
                raise e

        if not profile_exists:
            try:
                instance_profile = self.iam.create_instance_profile(self.role)
                self.log.info('Created IAM Profile {profile}'.format(
                                profile = self.role))

            except Exception, e:
                self.log.error(str(e))
                raise e

        try:
            role = self.iam.get_role(self.role)
            role_exists = True
        except Exception, e:
            if '404 Not Found' in str(e):
                pass
            else:
                self.log.error(str(e))
                raise e

        if not role_exists:

            try:
                role = self.iam.create_role(self.role)
                self.log.info('Created IAM Role {role}'.format(role = self.role))
                self.iam.add_role_to_instance_profile(self.role, self.role)
                self.log.info('Attached Role {role} to Profile {profile}'.format(
                            role = self.role, profile = self.role))

            except Exception, e:
                self.log.error(str(e))
                raise e

        role_policies = self.iam.list_role_policies(self.role)
        response = role_policies['list_role_policies_response']
        result = response['list_role_policies_result']
        existing_policies = result['policy_names']

        self.log.info('Existing policies: {policies}'.format(policies=existing_policies))

        for policy in self.IAM_ROLE_POLICIES:

            self.log.info('Processing policy "{policy}"'.format(policy=policy))

            if policy not in existing_policies:

                self.log.info('Policy "{policy}" does not exist'.format(
                                        policy = policy))

                try:
                    self.iam.put_role_policy(self.role, policy, policies[policy])

                    self.log.info('Added policy "{policy}"'.format(
                                        policy = policy))
                except Exception, e:
                    self.log.error(str(e))
                    raise e

            else:

                self.log.info('Policy "{policy}" already exists'.format(
                                        policy = policy))

                tyr_copy = json.loads(policies[policy])

                aws_copy = self.iam.get_role_policy(self.role, policy)
                aws_copy = aws_copy['get_role_policy_response']
                aws_copy = aws_copy['get_role_policy_result']
                aws_copy = aws_copy['policy_document']
                aws_copy = urllib.unquote(aws_copy)
                aws_copy = json.loads(aws_copy)

                if tyr_copy == aws_copy:
                    self.log.info('Policy "{policy}" is accurate'.format(
                                        policy = policy))

                else:

                    self.log.warn('Policy "{policy}" has been modified'.format(
                                        policy = policy))

                    try:
                        self.iam.delete_role_policy(self.role, policy)

                        self.log.info('Removed policy "{policy}"'.format(
                                            policy = policy))
                    except Exception, e:
                        self.log.error(str(e))
                        raise e

                    try:
                        self.iam.put_role_policy(self.role, policy, policies[policy])

                        self.log.info('Added policy "{policy}"'.format(
                                            policy = policy))
                    except Exception, e:
                        self.log.error(str(e))
                        raise e

    def establish_ec2_connection(self):

        self.log.info('Using EC2 Region "{region}"'.format(
                        region=self.region))
        self.log.info("Attempting to connect to EC2")

        try:
            self.ec2 = boto.ec2.connect_to_region(self.region)
            self.log.info('Established connection to EC2')
        except Exception, e:
            self.log.error(str(e))
            raise e

    def establish_iam_connection(self):

        try:
            self.iam = boto.connect_iam()
            self.log.info('Established connection to IAM')
        except Exception, e:
            self.log.error(str(e))
            raise e

    def establish_route53_connection(self):

        try:
            self.route53 = boto.route53.connect_to_region(self.region)
            self.log.info('Established connection to Route53')
        except Exception, e:
            self.log.error(str(e))
            raise e

    def launch(self, wait=False):

        parameters = {
                'image_id': self.ami,
                'instance_profile_name': self.role,
                'key_name': self.keypair,
                'instance_type': self.instance_type,
                'security_groups': self.security_groups,
                'block_device_map': self.blockdevicemapping,
                'user_data': self.user_data,
                'placement': self.availability_zone}

        reservation = self.ec2.run_instances(**parameters)

        self.log.info('Successfully launched EC2 instance')

        self.instance = reservation.instances[0]

        if wait:
            self.log.info('Waiting until the instance is running to return')

            state = self.instance.state

            while not(state == 'running'):
                try:
                    self.instance.update()
                    state = self.instance.state
                except Exception:
                    pass

            self.log.info('The instance is running')
            return

    def tag(self):
        self.ec2.create_tags([self.instance.id], self.tags)
        self.log.info('Tagged instance with {tags}'.format(tags = self.tags))

    def route(self):
        zone_address = self.hostname[len(self.name)+1:]

        self.log.info('Using Zone Address {address}'.format(
                            address = zone_address))

        try:
            zone = self.route53.get_zone(zone_address)
            self.log.info('Retrieved zone from Route53')
        except Exception, e:
            self.log.error(str(e))
            raise e

        name = self.hostname + '.'
        self.log.info('Using record name {name}'.format(name = name))
        self.log.info('Using record value {value}'.format(
                        value = self.instance.public_dns_name))

        if zone.get_cname(name) is None:
            self.log.info('The CNAME record does not exist')
            try:
                zone.add_cname(name, self.instance.public_dns_name)
                self.log.info('Created new CNAME record')
            except Exception, e:
                self.log.error(str(e))
                raise e
        else:
            self.log.info('The CNAME record already exists')
            zone.update_cname(name, self.instance.public_dns_name)
            self.log.info('Updated the CNAME record')

    @property
    def connection(self):

        try:
            connection = self.ssh_connection

            self.log.info('Determining is SSH transport is still active')
            transport = connection.get_transport()

            if not transport.is_active():
                self.log.warn('SSH transport is no longer active')
                self.log.info('Proceeding to re-establish SSH connection')
                raise Exception()

            else:
                self.log.info('SSH transport is still active')
                return connection
        except Exception:
            pass

        connection = SSHClient()
        connection.set_missing_host_key_policy(AutoAddPolicy())

        self.log.info('Attempting to establish SSH connection')

        while True:
            try:
                connection.connect(self.instance.public_dns_name,
                                    username = 'ec2-user')
                break
            except Exception:
                self.log.warn('Unable to establish SSH connection')
                time.sleep(10)

        self.log.info('Successfully established SSH connection')

        self.ssh_connection = connection

        return connection

    def run(self, command):

        with self.connection as conn:

            state = {
                        'in': None,
                        'out': None,
                        'err': None
                    }

            stdin, stdout, stderr = conn.exec_command(command)

            try:
                state['in'] = stdin.read()
            except IOError:
                pass

            try:
                state['out'] = stdout.read()
            except IOError:
                pass

            try:
                state['err'] = stderr.read()
            except IOError:
                pass

            return state

    def bake(self):

        chef_path = os.path.expanduser(self.chef_path)
        self.chef_api = chef.autoconfigure(chef_path)

        with self.chef_api:
            try:
                node = chef.Node(self.name)
                node.delete()

                self.log.info('Removed previous chef node "{node}"'.format(
                                node = self.name))
            except chef.exceptions.ChefServerNotFoundError:
                pass
            except Exception as e:
                self.log.error(str(e))
                raise e

            try:
                client = chef.Client(self.name)
                client = client.delete()

                self.log.info('Removed previous chef client "{client}"'.format(
                                client = self.name))
            except chef.exceptions.ChefServerNotFoundError:
                pass
            except Exception as e:
                self.log.error(str(e))
                raise e

            node = chef.Node.create(self.name)

            self.chef_node = node

            self.log.info('Created new Chef Node "{node}"'.format(
                                node = self.name))

            self.chef_node.chef_environment = self.environment

            self.log.info('Set the Chef Environment to "{env}"'.format(
                        env = self.chef_node.chef_environment))

            self.chef_node.run_list = self.CHEF_RUNLIST

            self.log.info('Set Chef run list to {list}'.format(
                                            list = self.chef_node.run_list))

            self.chef_node.save()
            self.log.info('Saved the Chef Node configuration')

    def baked(self):

        self.log.info('Determining status of "{node}"'.format(
                                            node = self.hostname))

        self.log.info('Waiting for Chef Client to start')

        while True:
            r = self.run('ls -l /var/log')

            if 'chef-client.log' in r['out']:
                break
            else:
                time.sleep(10)

        self.log.info('Chef Client has started')

        self.log.info('Waiting for Chef Client to finish')

        while True:
            r = self.run('pgrep chef-client')

            if len(r['out']) > 0:
                time.sleep(10)
            else:
                break

        self.log.info('Chef Client has finished')

        self.log.info('Determining Node state')

        r = self.run('tail /var/log/chef-client.log')

        if 'Chef Run complete in' in r['out']:
            self.log.info('Chef Client was successful')
            return True
        else:
            self.log.info('Chef Client was not successful')
            self.log.debug(r['out'])
            return False

    def autorun(self):

        self.establish_logger()
        self.configure()
        self.launch(wait=True)
        self.tag()
        self.route()
        self.bake()
