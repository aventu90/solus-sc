#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
#  This file is part of solus-sc
#
#  Copyright © 2013-2016 Ikey Doherty <ikey@solus-project.com>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 2 of the License, or
#  (at your option) any later version.
#

import gi
gi.require_version('Notify', '0.7')
from gi.repository import Gio, GObject, Notify

import comar
import pisi.db
import pisi.api
from operator import attrgetter

SC_UPDATE_APP_ID = "com.solus_project.UpdateChecker"


class ScUpdateObject(GObject.Object):
    """ Keep glib happy and allow us to store references in a liststore """

    old_pkg = None
    new_pkg = None

    # Simple, really.
    has_security_update = False

    __gtype_name__ = "ScUpdateObject"

    def __init__(self, old_pkg, new_pkg):
        GObject.Object.__init__(self)
        self.old_pkg = old_pkg
        self.new_pkg = new_pkg

        if not self.old_pkg:
            return
        oldRelease = int(self.old_pkg.release)
        histories = self.get_history_between(oldRelease, self.new_pkg)

        # Initial security update detection
        securities = [x for x in histories if x.type == "security"]
        if len(securities) < 1:
            return
        self.has_security_update = True

    def is_security_update(self):
        """ Determine if the update introduces security fixes """
        return self.has_security_update

    def get_history_between(self, old_release, new):
        """ Get the history items between the old release and new pkg """
        ret = list()

        for i in new.history:
            if int(i.release) <= int(old_release):
                continue
            ret.append(i)
        return sorted(ret, key=attrgetter('release'), reverse=True)


class ScUpdateApp(Gio.Application):

    pmanager = None
    link = None
    had_init = False
    net_mon = None
    notification = None

    def __init__(self):
        Gio.Application.__init__(self,
                                 application_id=SC_UPDATE_APP_ID,
                                 flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        """ Initial app activation """
        if self.had_init:
            return
        self.had_init = True
        Notify.init("Solus Update Service")
        self.net_mon = Gio.NetworkMonitor.get_default()
        self.load_comar()
        self.begin_background_checks()

    def action_show_updates(self, notification, action, user_data):
        """ Open the updates view """
        print("TOTES OPENING IT I SWEAR.")
        notification.close()

    def begin_background_checks(self):
        """ Initialise the actual background checks and initial update """
        self.reload_repos()
        pass

    def load_comar(self):
        """ Load the d-bus comar link """
        self.link = comar.Link()
        self.pmanager = self.link.System.Manager['pisi']
        self.link.listenSignals("System.Manager", self.pisi_callback)

    def pisi_callback(self, package, signal, args):
        """ Just let us know that things are done """
        if signal in ["finished", None]:
            self.check_updates()
        elif signal.startswith("tr.org.pardus.comar.Comar.PolicyKit"):
            self.eval_connection()

    def reload_repos(self):
        """ Actually refresh the repos.. """
        self.pmanager.updateAllRepositories()

    def can_update(self):
        """ Determine if policy/connection allows checking for updates """
        if not self.net_mon.get_network_available():
            return False
        return True

    def check_updates(self):
        """ Check the actual update availability - post refresh """
        if not self.can_update():
            # TODO: Update GSettings with last timestamp
            return
        upds = None
        try:
            upds = pisi.api.list_upgradable()
        except:
            return
        if not upds or len(upds) < 1:
            return

        idb = pisi.db.installdb.InstallDB()
        pdb = pisi.db.packagedb.PackageDB()

        security_ups = []
        for up in upds:
            # Might be obsolete, skip it
            if not pdb.has_package(up):
                continue
            candidate = pdb.get_package(up)
            old_pkg = None
            if idb.has_package(up):
                old_pkg = idb.get_package(up)
            sc = ScUpdateObject(old_pkg, candidate)
            if sc.is_security_update():
                security_ups.append(sc)

        if len(security_ups) > 0:
            title = "Security updates available"
            body = "Update at your earliest convenience to ensure continued " \
                   "security of your device"
            icon_name = "software-update-urgent-symbolic"
        else:
            title = "Software updates available"
            body = "New software updates are available for your device"
            icon_name = "software-update-available-symbolic"

        self.notification = Notify.Notification.new(title, body, icon_name)
        self.notification.set_timeout(12000)
        self.notification.add_action("open-sc", "Open Software Center", self.action_show_updates)
        self.notification.show()

    def eval_connection(self):
        """ Check if networking actually works """
        pass