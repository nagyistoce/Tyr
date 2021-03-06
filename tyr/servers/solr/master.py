from tyr.servers.server import Server


class SolrMasterNode(Server):

    SERVER_TYPE = 'solr'
    CHEF_RUNLIST = ['role[RoleSolr]']
    IAM_ROLE_POLICIES = [
        'allow-volume-control',
        'allow-get-solr-schema'
    ]

    def __init__(self, group=None, server_type=None, instance_type=None,
                 environment=None, ami=None, region=None, role=None,
                 keypair=None, availability_zone=None, security_groups=None,
                 block_devices=None, chef_path=None, subnet_id=None,
                 dns_zones=None, platform=None, use_latest_ami=False,
                 ingress_groups_to_add=None, ports_to_authorize=None,
                 classic_link=False, add_route53_dns=True,
                 chef_server_url=None):

        if server_type is None:
            server_type = self.SERVER_TYPE

        super(SolrMasterNode, self).__init__(group, server_type, instance_type,
                                             environment, ami, region, role,
                                             keypair, availability_zone,
                                             security_groups, block_devices,
                                             chef_path, subnet_id, dns_zones,
                                             platform, use_latest_ami,
                                             ingress_groups_to_add,
                                             ports_to_authorize, classic_link,
                                             add_route53_dns, chef_server_url)

    def set_chef_attributes(self):
        super(SolrMasterNode, self).set_chef_attributes()
        self.CHEF_ATTRIBUTES['solr'] = {}

        self.CHEF_ATTRIBUTES['solr']['is_master'] = 'true'
        self.log.info('Set solr.is_master to True')

        self.CHEF_ATTRIBUTES['solr']['group'] = self.group
        self.log.info('Set solr.group to {group}'.format(group=self.group))

        self.CHEF_ATTRIBUTES['solr']['master_host'] = self.hostname
        self.log.info('Set solr.master_host to {master}'.format(
            master=self.hostname)
        )

    def configure(self):
        super(SolrMasterNode, self).configure()
        self.set_chef_attributes()

        self.security_groups = [
            'management',
            'chef-nodes',
            self.envcl,
            '{env}-solr-management'.format(env=self.environment[0])
        ]

        self.resolve_security_groups()
