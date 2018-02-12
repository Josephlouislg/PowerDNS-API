import urllib2

import dns.resolver


class Dns:
    def __init__(self, own_dns, resolver, nameservers=[], a_records=[]):
        """
        nameservers example:
        ['a.iana-servers.net.', 'b.iana-servers.net.']
        """
        self.own_dns = own_dns
        self.resolver = resolver
        self.nameservers = nameservers
        if self.own_dns.domain != self.resolver.domain:
            raise Exception('Resolver and PowerDNS instances have different domains')
        if nameservers:
            self.resolver.config['NS'] = nameservers
        if a_records:
            self.resolver.config['A'] = a_records

    def create_zone(self):
        if self.nameservers:
            self.own_dns.create_zone(self.nameservers)
        else:
            try:
                self.own_dns.create_zone(self.resolver.config['NS'])
            except KeyError:
                raise Exception('NS records are empty')

    def copy_config(self):
        self.own_dns.copy_records_to_zone(self.resolver.config)

    def create_zone_file(self):
        self.resolver.create_bind_file()

    def update_records(self, name=''):
        self.own_dns.update_records(self.resolver.config, name=name)


class PowerDNS:
    def __init__(self,
                 DNS_HOST='127.0.0.1',
                 DNS_PORT='8088',
                 AUTHORIZATION_KEY='somekey',
                 domain='example.com',
                 ttl=86400,
                 name = ''
                 ):
        self.DNS_HOST = DNS_HOST
        self.DNS_PORT = DNS_PORT
        self.AUTHORIZATION_KEY = AUTHORIZATION_KEY
        self.domain = domain
        self.headers =  {'X-API-Key': self.AUTHORIZATION_KEY}
        self.api_url = r'http://%s:%s/%s' % (self.DNS_HOST, self.DNS_PORT, r"api/v1/servers/localhost/zones")
        self.zone_url = self.api_url + '/' + self.domain + '.'
        self.ttl = ttl
        try:
            self.config = self.__get_config()
        except:
            self.config = None

    def create_zone(self, nameservers=[], masters=[]):
        if not self.config:
            data = {
             'name': self.domain + '.',
             'kind':'Native',
             'masters': [],
             'nameservers': nameservers
             }
            request = urllib2.Request(self.api_url, headers=self.headers, data=json.dumps(data))
            request.get_method = lambda: 'POST'
            urllib2.urlopen(request)
            self.config = self.__get_config()
        else:
            return True

    def delete_zone(self):
        request = urllib2.Request(self.zone_url, headers=self.headers)
        request.get_method = lambda: 'DELETE'
        urllib2.urlopen(request)

    def __get_rrsets(self, config, changetype=None, name='', ttl=None):
        """
        config example:
        {
            "A": ['93.184.216.34', ...],
            "SOA": ['sns.dns.icann.org. noc.dns.icann.org. 2017102403 7200 3600 1209600 3600'].
        }
        """
        if not name:
            name = self.domain + '.'
        elif name[-1] != '.':
            name = name + '.'
        if not ttl:
            ttl=self.ttl
        rrsets = []
        for id in config:
            records = []
            for record in config[id]:
                records.append(
                        {
                            "content": record,
                            "disabled": False
                        }
                    )
            if changetype:
                rrsets.append(
                        {
                            "name": name,
                            "ttl": ttl,
                            "changetype": changetype,
                            "type": id,
                            "records": records
                        }
                    )
            else:
                rrsets.append(
                        {
                            "name": name,
                            "ttl": ttl,
                            "type": id,
                            "records": records
                        }
                    )
        return rrsets

    def copy_records_to_zone(self, config):
        if self.config:
            rrsets = self.__get_rrsets(config, changetype="REPLACE")
            request = urllib2.Request(self.zone_url, headers=self.headers, data=json.dumps({"rrsets":rrsets}))
            request.get_method = lambda: 'PATCH'
            resp = urllib2.urlopen(request)
            self.config = self.__get_config()
            return resp
        else:
            raise Exception('Zone doesnt exist')

    def __get_config(self):
            request = urllib2.Request(self.zone_url, headers=self.headers)
            return json.loads(urllib2.urlopen(request).read())

    def save_config(self):
        """
        config["rrsets"] example:
        config["rrsets"]= [
                            {
                             "comments": [],
                             "name": "example.com.",
                              "records":
                                         [
                                            {"content": "dnsserver.domain.com. hostmaster.example.com. 2017102701 10800 3600 604800 3600", "disabled": false}], 
                                            "ttl": 3600,
                                            "type": "SOA"},
                                        ]
                            }
                        ]
        """
        for item in self.config['rrsets']:
            item['changetype'] = 'REPLACE'
        request = urllib2.Request(self.zone_url, headers=self.headers, data=json.dumps({"rrsets":self.config["rrsets"]}))
        request.get_method = lambda: 'PATCH'
        try:
            resp = urllib2.urlopen(request)
        except urllib2.HTTPError as e:
            return e.reason

        self.config = self.__get_config()

    def update_records(self, records, name='', ttl=None):
        """
        records example:
        records = {
            "A": ['93.184.216.34'],
            "SOA": ['sns.dns.icann.org. noc.dns.icann.org. 2017102403 7200 3600 1209600 3600'].
            
            }
        """
        if self.config:
            rrsets = self.__get_rrsets(records, name=name, ttl=ttl)
            doesnt_exist = True
            for rrset in rrsets:
                if rrset in self.config["rrsets"]:
                    self.config["rrsets"][self.config['rrsets'].index(rrset)] = rrset
                else:
                    for config_rrset in self.config["rrsets"]:
                        if (config_rrset['type'] == rrset['type']) and (config_rrset['name'] == rrset['name']):
                            config_rrset['records'].extend(filter(lambda r: not (r in config_rrset['records']), rrset['records']))
                            doesnt_exist = False
                    if doesnt_exist:
                        self.config['rrsets'].append(rrset)
            return self.save_config()
        else:
            raise Exception('Zone does not exist')

    def delete_records(self, records):
        """
        records example:
        records = {
            "A": ['93.184.216.34'],
            "SOA": ['sns.dns.icann.org. noc.dns.icann.org. 2017102403 7200 3600 1209600 3600'].
            }
        """
        if self.config:
            for id in records:
                for rrset in self.config['rrsets']:
                    if rrset['type'] == id:
                        for record_for_delete in records[id]:
                            for record in rrset['records']:
                                if record['content'] == record_for_delete:
                                    rrset['records'].remove(record)
            self.save_config()
        else:
            raise Exception('Zone does not exist')


class Resolver:
    def __init__(self, domain='example.com', ttl=86400):
        self.ids = [
            'NONE',
            'SOA',
            'NS',
            'MX',
            'A',
            'MD',
            'MF',
            'CNAME',
            'MB',
            'MG',
            'MR',
            'NULL',
            'WKS',
            'PTR',
            'HINFO',
            'MINFO',
            'TXT',
            'RP',
            'AFSDB',
            'X25',
            'ISDN',
            'RT',
            'NSAP',
            'NSAP-PTR',
            'SIG',
            'KEY',
            'PX',
            'GPOS',
            'AAAA',
            'LOC',
            'NXT',
            'SRV',
            'NAPTR',
            'KX',
            'CERT',
            'A6',
            'DNAME',
            'OPT',
            'APL',
            'DS',
            'SSHFP',
            'IPSECKEY',
            'RRSIG',
            'NSEC',
            'DNSKEY',
            'DHCID',
            'NSEC3',
            'NSEC3PARAM',
            'TLSA',
            'HIP',
            'CDS',
            'CDNSKEY',
            'CSYNC',
            'SPF',
            'UNSPEC',
            'EUI48',
            'EUI64',
            'TKEY',
            'TSIG',
            'IXFR',
            'AXFR',
            'MAILB',
            'MAILA',
            'ANY',
            'URI',
            'CAA',
            'TA',
            'DLV',
        ]
        self.domain = domain
        self.ttl = ttl
        self.config = self.__load_config()

    def create_bind_file(self):
        if  self.config:
            ns_ips = []
            mx_ips = []
            f = open(self.domain, 'w')
            f.write('$ORIGIN %s. \n$TTL %d\n'%(self.domain, self.ttl))
            try:
                f.write('@      IN  SOA ' + reduce(lambda x,y:x+' '+y, self.config['SOA']))
            except KeyError:
                f.close()
                raise Exception("Cant get SOA record")
            for id in self.ids:
                try:
                    if id!='SOA' and self.config[id]:
                        f.write('\n;;'+id+' records \n')
                        if id=='A':
                            for ip in ns_ips + mx_ips:
                                for address in ip['ip']:
                                    f.write(ip['name']+'     IN '+id+ '  '+ address + '\n')
                        for record in self.config[id]:
                            if id == 'NS':
                                f.write('     IN '+id+ '  '+ record + '\n')
                                answers = dns.resolver.query(record, 'A')
                                ns_ips.append({'name':record, 'ip':map(lambda a:a.to_text(), answers)})
                            elif id == 'MX':
                                domain = record.split(' ')[1]
                                answers = dns.resolver.query(domain, 'A')
                                mx_ips.append({'name':domain, 'ip':map(lambda a:a.to_text(), answers)})
                                f.write(self.domain+'     IN '+id+ '  '+ record + '\n')
                            else:
                                f.write(self.domain+'     IN '+id+ '  '+ record + '\n')
                except KeyError:
                    pass
            f.close()

    def __load_config(self):
        config = {}
        for a in self.ids:
            try:
                answers = dns.resolver.query(self.domain, a)
                config[a] = map(lambda a:a.to_text(), answers)
            except Exception as e:
                pass
        return config
