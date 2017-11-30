#
# Copyright (C) 2013  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
# Red Hat Author(s): Vratislav Podzimek <vpodzime@redhat.com>
#

"""Module with the RocksRollsData class."""

import os.path
import logging
import subprocess

from pyanaconda.addons import AddonData
from pyanaconda.iutil import getSysroot
from pyanaconda import kickstart
from pyanaconda import nm 
from org_rocks_rolls import RocksEnv

from pykickstart.options import KSOptionParser
from pykickstart.errors import KickstartParseError, formatErrorMsg

# export RocksRolls class to prevent Anaconda's collect method from taking
# AddonData class instead of the HelloWorldData class
# :see: pyanaconda.kickstart.AnacondaKSHandler.__init__
__all__ = ["RocksRollsData"]

ROLLS_FILE_PATH = "/root/rocks-rolls.txt"

class RocksRollsData(AddonData):
    """
    Class parsing and storing data for the Hello world addon.

    :see: pyanaconda.addons.AddonData

    """

    def __init__(self, name):
        """
        :param name: name of the addon
        :type name: str

        """

        AddonData.__init__(self, name)
        self.text = ""
        self.reverse = False
        self.postscripts = None
        self.haverolls = None
        self.clientInstall = RocksEnv.RocksEnv().clientInstall

    def __str__(self):
        """
        What should end up in the resulting kickstart file, i.e. the %addon
        section containing string representation of the stored data.

        """

        addon_str = "%%addon %s" % self.name

        if self.reverse:
            addon_str += " --reverse"

        addon_str += "\n%s\n%%end\n" % self.text

        if self.postscripts is not None:
            addon_str += self.postscripts

        return addon_str

    def handle_header(self, lineno, args):
        """
        The handle_header method is called to parse additional arguments in the
        %addon section line.

        args is a list of all the arguments following the addon ID. For
        example, for the line:

            %addon org_fedora_hello_world --reverse --arg2="example"

        handle_header will be called with args=['--reverse', '--arg2="example"']

        :param lineno: the current line number in the kickstart file
        :type lineno: int
        :param args: the list of arguments from the %addon line
        :type args: list
        """

        op = KSOptionParser()
        op.add_option("--reverse", action="store_true", default=False,
                dest="reverse", help="Reverse the display of the addon text")
        (opts, extra) = op.parse_args(args=args, lineno=lineno)

        # Reject any additional arguments.
        if extra:
            msg = "Unhandled arguments on %%addon line for %s" % self.name
            if lineno != None:
                raise KickstartParseError(formatErrorMsg(lineno, msg=msg))
            else:
                raise KickstartParseError(msg)

        # Store the result of the option parsing
        self.reverse = opts.reverse

    def handle_line(self, line):
        """
        The handle_line method that is called with every line from this addon's
        %addon section of the kickstart file.

        :param line: a single line from the %addon section
        :type line: str

        """

        # simple example, we just append lines to the text attribute
        if self.text is "":
            self.text = line.strip()
        else:
            self.text += " " + line.strip()

    def finalize(self):
        """
        The finalize method that is called when the end of the %addon section
        (i.e. the %end line) is processed. An addon should check if it has all
        required data. If not, it may handle the case quietly or it may raise
        the KickstartValueError exception.

        """

        # no actions needed in this addon
        pass

    def setup(self, storage, ksdata, instclass):
        """
        The setup method that should make changes to the runtime environment
        according to the data stored in this object.

        :param storage: object storing storage-related information
                        (disks, partitioning, bootloader, etc.)
        :type storage: blivet.Blivet instance
        :param ksdata: data parsed from the kickstart file and set in the
                       installation process
        :type ksdata: pykickstart.base.BaseHandler instance
        :param instclass: distribution-specific information
        :type instclass: pyanaconda.installclass.BaseInstallClass
        """

        log = logging.getLogger("anaconda")
        log.info("ROCKS KS SETUP: %s" % ksdata.__str__()) 

        ## At this point rolls have been selected, the in-memory rocks database
        ## is set up and cluster information has been added by the user. now
        ## need to
        ##   A. add the attributes from ksdata.addons.org_rocks_rolls.info
        ##      into the in-memory database
        ##   B. rolls are in  ksdata.addons.org_rocks_rolls.rolls 
        ##      process the xml files for the rolls specified, then generate
        ##      packages

        ## We don't have "rolls" if we are a clientInstall
        if self.clientInstall or ksdata.addons.org_rocks_rolls.info is None:
            return
        for row in ksdata.addons.org_rocks_rolls.info:
            log.info("ROCKS ADD ATTR %s=%s" % (row[2],row[1]))
            self.addAttr(row[2],row[1])
        cmd = ["/opt/rocks/bin/rocks","report","host","attr","pydict=true"]
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE)
        attrs = p.stdout.readlines()[0].strip()
        
        f = open("/tmp/site.attrs","w")
        atdict = eval(attrs)
        for key in atdict.keys():
            f.write( "%s:%s\n" % (key,atdict[key]) )
        f.close()

        ## Write out all of the Ethernet devices so that we can load
        ## Load into the installed FE database. See database-data.xm
        etherifs = filter(lambda x: nm.nm_device_type_is_ethernet(x),\
           nm.nm_devices())
        ethermacs = map(lambda x: nm.nm_device_perm_hwaddress(x),etherifs)
        g = open("/tmp/frontend-ifaces.sh","w")
        g.write("/opt/rocks/bin/rocks config host interface localhost iface='%s' mac='%s' flag='' module=''\n" % \
            (",".join(etherifs),",".join(ethermacs)))
        g.close()

        cmd = ["/opt/rocks/bin/rocks","list","node", "xml", \
           "attrs=%s" % attrs, "basedir=/tmp/rocks/export/profile", "server"]
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE)
        nodexml = p.stdout.readlines()

        cmd = ["/opt/rocks/sbin/kgen","--section=packages"]
        p = subprocess.Popen(cmd,stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        out,err = p.communicate(input="".join(nodexml))
        pkgs = filter(lambda x: len(x) > 0, out.split("\n")) 

        for pkg in pkgs:
            if "%" in pkg or "#" in pkg:
                continue
            if not pkg in ksdata.packages.packageList:
                ksdata.packages.packageList.append(pkg)

        ## Generate the post scripts section
        log.info("ROCKS GENERATING POST SCRIPTS")
        cmd = ["/opt/rocks/sbin/kgen","--section=post"]
        p = subprocess.Popen(cmd,stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.postscripts,err = p.communicate(input="".join(nodexml))
        log.info("ROCKS POST SCRIPTS GENERATED")

        ksparser = kickstart.AnacondaKSParser(ksdata)
        ksparser.readKickstartFromString(self.postscripts, reset=False)

        ## Add eula and firstboot stanzas 
        log.info("ROCKS FIRSTBOOT/EULA")
        ksparser = kickstart.AnacondaKSParser(ksdata)
        ksparser.readKickstartFromString("eula --agreed", reset=False)
        ksparser.readKickstartFromString("firstboot --disable", reset=False)
        log.info("ROCKS FIRSBOOT/EULA END ")
    def addAttr(self,attr,value):
        if value is None or attr is None:
            return
        cmd=["/opt/rocks/bin/rocks","add","attr",attr,value]
        p1 = subprocess.Popen(cmd,stdout=subprocess.PIPE)
        p1.communicate() 

    def execute(self, storage, ksdata, instclass, users):
        """
        The execute method that should make changes to the installed system. It
        is called only once in the post-install setup phase.

        :see: setup
        :param users: information about created users
        :type users: pyanaconda.users.Users instance

        """

        rolls_file_path = os.path.normpath(getSysroot() + ROLLS_FILE_PATH)
        with open(rolls_file_path, "w") as fobj:
            fobj.write("%s\n" % self.text)
