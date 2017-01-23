# -*- coding: utf-8 -*-
import io

from sslyze.plugins.utils.certificate import Certificate
from typing import Dict
from typing import List
from typing import Optional


class TrustStore(object):

    def __init__(self, path, name, version, ev_oids=None):
        # type: (unicode, unicode, unicode, Optional[List[unicode]]) -> None
        self.path = path
        self.name = name
        self.version = version
        self._ev_oids = []
        if ev_oids:
            self._ev_oids = ev_oids

        self._subject_to_certificate_dict = None


    def is_extended_validation(self, certificate):
        # type: (Certificate) -> bool
        """Is the supplied server certificate EV ?
        """
        if not self._ev_oids:
            raise ValueError(u'No EV OIDs supplied for {} store - cannot detect EV certificates'.format(self.name))

        is_ev = False
        try:
            policy = certificate.as_dict['extensions']['X509v3 Certificate Policies']['Policy']
        except:
            # Certificate which don't have this extension
            pass
        else:
            if policy[0] in self._ev_oids:
                is_ev = True
        return is_ev


    def _compute_subject_certificate_dict(self):
        cert_dict = {}
        with io.open(self.path) as store_file:
            store_content = store_file.read()
            # Each certificate is separated by two new lines and there are
            pem_cert_list = store_content.split(u'\n\n')[1::]
            for pem_split in pem_cert_list:
                # Remove comments as they may cause Unicode errors
                final_pem = u'-----BEGIN CERTIFICATE-----{}-----END CERTIFICATE-----'.format(
                    pem_split.split(u'-----BEGIN CERTIFICATE-----')[1].split(u'-----END CERTIFICATE-----')[0]
                )
                cert = Certificate.from_pem(final_pem)
                # Store a dictionary of subject->certificate for easy lookup
                cert_dict[self._hash_subject(cert.as_dict['subject'])] = cert
            return cert_dict


    @staticmethod
    def _hash_subject(certificate_subjet_dict):
        # type: (Dict) -> unicode
        hashed_subject = u''.join([u'{}{}'.format(key.decode(encoding='utf-8'), value.decode(encoding='utf-8'))
                                   for key, value in certificate_subjet_dict.items()])
        return hashed_subject


    def _get_certificate_with_subject(self, certificate_subject_dict):
        # type: (Dict) -> Certificate
        if self._subject_to_certificate_dict is None:
            self._subject_to_certificate_dict = self._compute_subject_certificate_dict()

        return self._subject_to_certificate_dict.get(self._hash_subject(certificate_subject_dict), None)


    @staticmethod
    def _is_certificate_chain_order_valid(certificate_chain):
        # type: (List[Certificate]) -> bool
        previous_issuer = None
        for index, cert in enumerate(certificate_chain):
            current_subject = cert.as_dict['subject']

            if index > 0:
                # Compare the current subject with the previous issuer in the chain
                if current_subject != previous_issuer:
                    return False
            try:
                previous_issuer = cert.as_dict['issuer']
            except KeyError:
                # Missing issuer; this is okay if this is the last cert
                previous_issuer = u"missing issuer {}".format(index)
        return True


    def build_verified_certificate_chain(self, received_certificate_chain):
        # type: (List[Certificate]) -> List[Certificate]
        """Try to figure out the verified chain by finding the anchor/root CA the received chain chains up to in the
        trust store.

        This will not clean the certificate chain if additional/invalid certificates were sent and the signatures and
        fields (notBefore, etc.) are not verified.
        """
        # The certificates must have been sent in the correct order or we give up
        if not self._is_certificate_chain_order_valid(received_certificate_chain):
            raise InvalidCertificateChainOrderError()

        # TODO: OpenSSL 1.1.0 has SSL_get0_verified_chain() to do this directly
        verified_certificate_chain = []
        anchor_cert = None
        # Assume that the certificates were sent in the correct order or give up
        for cert in received_certificate_chain:
            anchor_cert = self._get_certificate_with_subject(cert.as_dict['issuer'])
            verified_certificate_chain.append(cert)
            if anchor_cert:
                verified_certificate_chain.append(anchor_cert)
                break

        if anchor_cert is None:
            # Could not build the verified chain
            raise AnchorCertificateNotInTrustStoreError()

        return verified_certificate_chain


class CouldNotBuildVerifiedChainError(ValueError):
    pass

class AnchorCertificateNotInTrustStoreError(CouldNotBuildVerifiedChainError):
    pass

class InvalidCertificateChainOrderError(CouldNotBuildVerifiedChainError):
    pass
