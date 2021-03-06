from node import MongoNode


class MongoReplicaSetMember(MongoNode):

    REPLICA_SET_TEMPLATE = '{group}-rs{set_}'

    def __init__(self, group=None, server_type=None, instance_type=None,
                 environment=None, ami=None, region=None, role=None,
                 keypair=None, availability_zone=None,
                 security_groups=None, block_devices=None,
                 chef_path=None, subnet_id=None, dns_zones=None,
                 ingress_groups_to_add=None, ports_to_authorize=None,
                 classic_link=False, add_route53_dns=True, chef_server_url=None,
                 replica_set=None, mongodb_version=None):

        super(MongoReplicaSetMember, self).__init__(group, server_type,
                                                    instance_type,
                                                    environment, ami, region,
                                                    role, keypair,
                                                    availability_zone,
                                                    security_groups,
                                                    block_devices, chef_path,
                                                    subnet_id, dns_zones,
                                                    ingress_groups_to_add,
                                                    ports_to_authorize,
                                                    classic_link,
                                                    add_route53_dns,
                                                    chef_server_url,
                                                    mongodb_version)

        self.replica_set = replica_set

    def set_chef_attributes(self):
        super(MongoReplicaSetMember, self).set_chef_attributes()
        replica_set = self.REPLICA_SET_TEMPLATE.format(
            group=self.group, set_=self.replica_set)
        self.CHEF_ATTRIBUTES['mongodb']['replicaset_name'] = replica_set
        self.log.info('Set the replica set name to "{name}"'.format(
            name=replica_set)
        )

    def configure(self):
        super(MongoReplicaSetMember, self).configure()
        self.set_chef_attributes()

        if self.replica_set is None:
            self.log.warn('No replica set provided')
            self.replica_set = 1

        self.log.info('Using replica set {set}'.format(set=self.replica_set))

    @property
    def tags(self):

        tags = super(MongoReplicaSetMember, self).tags

        tags['ReplicaSet'] = self.REPLICA_SET_TEMPLATE.format(
            group=self.group, set_=self.replica_set
        )

        return tags
