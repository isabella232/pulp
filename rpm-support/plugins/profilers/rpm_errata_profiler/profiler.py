# -*- coding: utf-8 -*-
#
# Copyright © 2012 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

"""
Profiler plugin to support RPM Errata functionality
"""
import gettext

from pulp.plugins.model import ApplicabilityReport
from pulp.plugins.profiler import Profiler
from pulp.server.db.model.criteria import UnitAssociationCriteria
from pulp_rpm.yum_plugin import util

_ = gettext.gettext
_LOG = util.getLogger(__name__)

PROFILER_TYPE_ID="rpm_errata_profiler"
ERRATA_TYPE_ID="erratum"
RPM_TYPE_ID="rpm"
RPM_UNIT_KEY = ("name", "epoch", "version", "release", "arch", "checksum", "checksumtype")

# TODO:
# Consider test case of multiple errata
#  errata-A refers to pkg-1.0
#  errata-B refers to pkg-1.1
#  What do we do?  pkg-1.1 is the latest and should be the one included
#   we should detect pkg-1.1 and cull pkg-1.0 from list?

# Consider consumer is bound to repo and picks up errata-A
#  errata-A refers to pkg-A which is not part of the bound repos
#  What is the behavior?
#   For applicable, we can include it if something older than pkg-A was installed
#   For install_units, we can't include it since we can't form a unit_key for a pkg we can't see in DB
#    Do we silently drop the pkg, or do we raise an Exception, or something else?

class RPMErrataProfiler(Profiler):
    def __init__(self):
        super(RPMErrataProfiler, self).__init__()

    @classmethod
    def metadata(cls):
        return { 
                'id': PROFILER_TYPE_ID,
                'display_name': "RPM Errata Profiler",
                'types': [ERRATA_TYPE_ID],
                }

    def update_profile(self, consumer, profile, config, conduit):
        """
        Notification that the consumer has reported the installed unit
        profile.  The profiler has this opportunity to translate the
        reported profile.

        @param consumer: A consumer.
        @type consumer: L{pulp.server.plugins.model.Consumer}

        @param profile: The reported profile.
        @type profile: dict

        @param config: plugin configuration
        @type config: L{pulp.server.plugins.config.PluginCallConfiguration}

        @param conduit: provides access to relevant Pulp functionality
        @type conduit: L{pulp.plugins.conduits.profile.ProfilerConduit}

        @return: The translated profile.
        @rtype: dict
        """
        raise NotImplementedError()

    def install_units(self, consumer, units, options, config, conduit):
        """
        Translate the specified content units to be installed.
        The specified content units are intented to be installed on the
        specified consumer.  It is requested that the profiler translate
        the units as needed.

        @param consumer: A consumer.
        @type consumer: L{pulp.server.plugins.model.Consumer}

        @param units: A list of content units to be installed.
        @type units: list of:
            { type_id:<str>, unit_key:<dict> }

        @param options: Install options; based on unit type.
        @type options: dict

        @param config: plugin configuration
        @type config: L{pulp.server.plugins.config.PluginCallConfiguration}

        @param conduit: provides access to relevant Pulp functionality
        @type conduit: L{pulp.plugins.conduits.profile.ProfilerConduit}

        @return: The translated units
        @rtype: list
        """
        return self.translate_units(units, consumer, conduit)

    def update_units(self, consumer, units, options, config, conduit):
        """
        Translate the specified content units to be updated.
        The specified content units are intented to be updated on the
        specified consumer.  It is requested that the profiler translate
        the units as needed.

        @param consumer: A consumer.
        @type consumer: L{pulp.server.plugins.model.Consumer}

        @param units: A list of content units to be updated.
        @type units: list of:
            { type_id:<str>, unit_key:<dict> }

        @param options: Update options; based on unit type.
        @type options: dict

        @param config: plugin configuration
        @type config: L{pulp.server.plugins.config.PluginCallConfiguration}

        @param conduit: provides access to relevant Pulp functionality
        @type conduit: L{pulp.plugins.conduits.profile.ProfilerConduit}

        @return: The translated units
        @rtype: list
        """
        return self.translate_units(units, consumer, conduit)

    def uninstall_units(self, consumer, units, options, config, conduit):
        """
        Translate the specified content units to be uninstalled.
        The specified content units are intented to be uninstalled on the
        specified consumer.  It is requested that the profiler translate
        the units as needed.

        @param consumer: A consumer.
        @type consumer: L{pulp.server.plugins.model.Consumer}

        @param units: A list of content units to be uninstalled.
        @type units: list of:
            { type_id:<str>, unit_key:<dict> }

        @param options: Update options; based on unit type.
        @type options: dict
        
        @param config: plugin configuration
        @type config: L{pulp.server.plugins.config.PluginCallConfiguration}

        @param conduit: provides access to relevant Pulp functionality
        @type conduit: L{pulp.plugins.conduits.profile.ProfilerConduit}

        @return: The translated units
        @rtype: list
        """
        raise NotImplementedError()

    # -- applicability ---------------------------------------------------------


    def unit_applicable(self, consumer, unit, config, conduit):
        """
        Determine whether the content unit is applicable to
        the specified consumer.  The definition of "applicable" is content
        type specific and up to the descision of the profiler.

        @param consumer: A consumer.
        @type consumer: L{pulp.server.plugins.model.Consumer}

        @param unit: A content unit: { type_id:<str>, unit_key:<dict> }
        @type unit: dict

        @param config: plugin configuration
        @type config: L{pulp.server.plugins.config.PluginCallConfiguration}

        @param conduit: provides access to relevant Pulp functionality
        @type conduit: L{pulp.plugins.conduits.profile.ProfilerConduit}

        @return: An applicability report.
        @rtype: L{pulp.plugins.model.ApplicabilityReport}
        """
        applicable = False
        summary = {}
        details = {}
        summary["applicable_rpms"] = []
        summary["rpms_to_upgrade"] = {}
        if unit["type_id"] != ERRATA_TYPE_ID:
            _LOG.warn("unit_applicable invoked with type_id [%s], expected [%s]" % (unit["type_id"], ERRATA_TYPE_ID))
            return ApplicabilityReport(unit, applicable, summary, details)
        errata = self.find_unit_associated_to_consumer(unit['type_id'], unit['unit_key'], consumer, conduit)
        if not errata:
            _LOG.warn("Unable to find errata with unit_key [%s] in bound repos [%s] to consumer [%s]" % \
                    (unit["unit_key"], bound_repos, consumer.id))
            return ApplicabilityReport(unit, applicable, summary, details)
        #
        # Look at the rpms available from the errata and determine if they apply to
        # rpms installed on the consumer.
        #
        updated_rpms = self.get_rpms_from_errata(errata)
        applicable_rpms, upgrade_details = self.rpms_applicable_to_consumer(consumer, updated_rpms)
        summary["applicable_rpms"] = applicable_rpms
        details["rpms_to_upgrade"] = upgrade_details
        if applicable_rpms:
            applicable = True
        return ApplicabilityReport(unit, applicable, summary, details)

    # -- Below are helper methods not part of the Profiler interface ----

    def translate_units(self, units, consumer, conduit):
        """
        Translate a list of errata units into a list of rpm units
        """
        translated_units = []
        for unit in units:
            values = self.translate(unit, consumer, conduit)
            if values:
                translated_units.extend(values)
        return translated_units

    def translate(self, unit, consumer, conduit):
        """
        Translates an erratum to a list of rpm units
        The rpm units refer to the upgraded packages referenced by the erratum

        @param unit: A content unit: { type_id:<str>, unit_key:<dict> }
        @type unit: dict

        @param consumer: A consumer.
        @type consumer: L{pulp.server.plugins.model.Consumer}

        @param conduit: provides access to relevant Pulp functionality
        @type conduit: L{pulp.plugins.conduits.profile.ProfilerConduit}
        """
        errata = self.find_unit_associated_to_consumer(unit["type_id"], unit["unit_key"], consumer, conduit)
        if not errata:
            _LOG.warn("Unable to find errata with unit_key [%s] in bound repos [%s] to consumer [%s]" % \
                    (unit["unit_key"], conduit.get_bindings(consumer.id), consumer.id))
            return []
        updated_rpms = self.get_rpms_from_errata(errata)
        applicable_rpms, upgrade_details = self.rpms_applicable_to_consumer(consumer, updated_rpms)
        translated_units = []
        #
        # Translate each applicable rpm to an existing unit if it exists
        #
        for ar in applicable_rpms:
            unit_key = self.form_rpm_unit_key(ar)
            rpm_unit = self.find_unit_associated_to_consumer(RPM_TYPE_ID, unit_key, consumer, conduit)
            if rpm_unit:
                translated_units.append(rpm_unit)
        return translated_units

    def find_unit_associated_to_consumer(self, unit_type, unit_key, consumer, conduit):
        criteria = UnitAssociationCriteria(type_ids=[unit_type], unit_filters={"unit_key":unit_key})
        return self.find_unit_associated_to_consumer_by_criteria(criteria, consumer, conduit)

    def find_unit_associated_to_consumer_by_criteria(self, criteria, consumer, conduit):
        # We don't know what repo the unit could belong to
        # and we don't have a means for querying all repos at once
        # so we are iterating over each repo
        bound_repos = conduit.get_bindings(consumer.id)
        for repo in bound_repos:
            result = conduit.get_units(repo.id, criteria)
            if result:
                return result[0]
        return None

    def get_rpms_from_errata(self, errata):
        """
        @param errata
        @type errata: pulp.plugins.model.Unit

        @return list of rpms, which are each a dict of nevra info
        @rtype: [{}]
        """
        rpms = []
        if not errata.metadata.has_key("pkglist"):
            return rpms
        for pkgs in errata.metadata['pkglist']:
            for rpm in pkgs["packages"]:
                rpms.append(rpm)
        return rpms

    def rpms_applicable_to_consumer(self, consumer, errata_rpms):
        """
        @param consumer:
        @type consumer: L{pulp.server.plugins.model.Consumer}

        @param errata_rpms: 
        @type errata_rpms: list of dicts

        @return:    tuple, first entry list of dictionaries of applicable 
                    rpm entries, second entry dictionary with more info 
                    of which installed rpm will be upgraded by what rpm

                    Note:
                    This method does not take into consideration if the consumer
                    is bound to the repo containing the RPM.  We will rely on an
                    error being generated at a later install step if the consumer
                    is not bound to an appropriate repo.
        @rtype: ([{}], {})
        """
        applicable_rpms = []
        older_rpms = {}
        _LOG.info("Consumer <%s> has profiles with keys: %s" % (consumer.id, consumer.profiles.keys()))
        if not consumer.profiles.has_key(RPM_TYPE_ID):
            return applicable_rpms, older_rpms
        lookup = self.form_lookup_table(consumer.profiles[RPM_TYPE_ID])
        for errata_rpm in errata_rpms:
            key = "%s.%s" % (errata_rpm["name"], errata_rpm["arch"])
            if lookup.has_key(key):
                installed_rpm = lookup[key]
                if util.is_rpm_newer(errata_rpm, installed_rpm):
                    # Errata RPM is newer, ensure that checksum info is present
                    if not errata_rpm.has_key("sum"):
                        _LOG.warn("Unable to process rpm from errata for translation since it's missing checksum info. [%s]" % (errata_rpm))
                        continue
                    # We expect that most rpm dictionaries will contain checksum info as: 'checksum' and 'checksumtype'
                    # The rpm dictionaries embedded in an errata contains the data as 'sum' with a tuple of (checksumtype, checksum)
                    # We are converting from this errata embedded format to what the rest of Pulp expects
                    errata_rpm["checksum"] = errata_rpm["sum"][1]
                    errata_rpm["checksumtype"] = errata_rpm["sum"][0]
                    applicable_rpms.append(errata_rpm)
                    older_rpms[key] = {"installed":installed_rpm, "available":errata_rpm}
        return applicable_rpms, older_rpms

    def form_lookup_table(self, rpms):
        lookup = {}
        for r in rpms:
            # Assuming that only 1 name.arch is allowed to be installed on a machine
            # therefore we will handle only one name.arch in the lookup table
            key = "%s.%s" % (r["name"], r["arch"])
            lookup[key] = r
        return lookup

    def form_rpm_unit_key(self, rpm_dict):
        unit_key = {}
        for key in RPM_UNIT_KEY:
            unit_key[key] = rpm_dict[key]
        return unit_key

