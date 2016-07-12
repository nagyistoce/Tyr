from tyr.servers.server import Server


class ScriptsServer(Server):

    SERVER_TYPE = 'scripts'

    CHEF_RUNLIST = ['role[RoleScripts]']

    IAM_ROLE_POLICIES = [
        'allow-describe-instances',
        'allow-describe-tags',
        'allow-describe-elbs',
        'allow-describe-snapshots',
        'allow-get-hudl-config',
    ]

    def __init__(self, group=None, server_type=None, instance_type=None,
                 environment=None, ami=None, region=None, role=None,
                 keypair=None, availability_zone=None, security_groups=None,
                 block_devices=None, chef_path=None, subnet_id=None,
                 dns_zones=None, chef_server_url=None):

        if server_type is None:
            server_type = self.SERVER_TYPE

        if instance_type is None:
            instance_type = 't2.micro'

        super(ScriptsServer, self).__init__(group=group, server_type=server_type,
                                            instance_type=instance_type,
                                            environment=environment,
                                            ami=ami, region=region,
                                            role=role, keypair=keypair,
                                            availability_zone=availability_zone,
                                            security_groups=security_groups,
                                            block_devices=block_devices,
                                            chef_path=chef_path,
                                            subnet_id=subnet_id,
                                            dns_zones=dns_zones,
                                            chef_server_url=chef_server_url)

    def configure(self):
        super(ScriptsServer, self).configure()
