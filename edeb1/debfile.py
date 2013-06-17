"""  Copyright (c) 2005-2010 Canonical
  Author: Michael Vogt <michael.vogt@ubuntu.com>

  Revisions: Anthony "AntCer" Cervantes <bodhidocs@gmail.com>"""

import apt
import apt_inst
import apt_pkg
import gzip
import os
import sys

from apt_pkg import gettext as _
from StringIO import StringIO

class NoDebArchiveException(IOError):
    """Exception which is raised if a file is no Debian archive."""

class DebPackage(object):
    """A Debian Package (.deb file)."""

    # Constants for comparing the local package file with the version
    # in the cache
    (VERSION_NONE,
     VERSION_OUTDATED,
     VERSION_SAME,
     VERSION_NEWER) = range(4)

    debug = 0

    def __init__(self, filename=None, cache=None):
        if cache is None:
            cache = apt.Cache()
        self._cache = cache
        self._debfile = None
        self.pkgname = ""
        self._sections = {}
        self._need_pkgs = []
        self._check_was_run = False
        self._failure_string = ""
        self._multiarch = None
        if filename:
            self.open(filename)

    def open(self, filename):
        """ open given debfile """
        self._dbg(3, "open '%s'" % filename)
        self._need_pkgs = []
        self._installed_conflicts = set()
        self._failure_string = ""
        self.filename = filename
        self._debfile = apt_inst.DebFile(self.filename)
        control = self._debfile.control.extractdata("control")
        self._sections = apt_pkg.TagSection(control)
        self.pkgname = self._sections["Package"]
        self._check_was_run = False

    def __getitem__(self, key):
        return self._sections[key]

    @property
    def filelist(self):
        """return the list of files in the deb."""
        files = []
        try:
            self._debfile.data.go(lambda item, data: files.append(item.name))
        except SystemError:
            return [_("List of files for '%s' could not be read") %
                    self.filename]
        return files

    # helper that will return a pkgname with a multiarch suffix if needed
    def _maybe_append_multiarch_suffix(self, pkgname,
                                       in_conflict_checking=False):
        # trivial cases
        if not self._multiarch:
            return pkgname
        elif self._cache.is_virtual_package(pkgname):
            return pkgname
        elif (pkgname in self._cache and
              self._cache[pkgname].candidate.architecture == "all"):
            return pkgname
        # now do the real multiarch checking
        multiarch_pkgname = "%s:%s" % (pkgname, self._multiarch)
        # the upper layers will handle this
        if not multiarch_pkgname in self._cache:
            return multiarch_pkgname
        # now check the multiarch state
        cand = self._cache[multiarch_pkgname].candidate._cand
        #print pkgname, multiarch_pkgname, cand.multi_arch
        # the default is to add the suffix, unless its a pkg that can satify
        # foreign dependencies
        if cand.multi_arch & cand.MULTI_ARCH_FOREIGN:
            return pkgname
        # for conflicts we need a special case here, any not multiarch enabled
        # package has a implicit conflict
        if (in_conflict_checking and
            not (cand.multi_arch & cand.MULTI_ARCH_SAME)):
            return pkgname
        return multiarch_pkgname

    def _is_or_group_satisfied(self, or_group):
        """Return True if at least one dependency of the or-group is satisfied.

        This method gets an 'or_group' and analyzes if at least one dependency
        of this group is already satisfied.
        """
        self._dbg(2, "_checkOrGroup(): %s " % (or_group))

        for dep in or_group:
            depname = dep[0]
            ver = dep[1]
            oper = dep[2]

            # multiarch
            depname = self._maybe_append_multiarch_suffix(depname)

            # check for virtual pkgs
            if not depname in self._cache:
                if self._cache.is_virtual_package(depname):
                    self._dbg(3, "_is_or_group_satisfied(): %s is virtual dep" % depname)
                    for pkg in self._cache.get_providing_packages(depname):
                        if pkg.is_installed:
                            return True
                continue
            # check real dependency
            inst = self._cache[depname].installed
            if inst is not None and apt_pkg.check_dep(inst.version, oper, ver):
                return True

            # if no real dependency is installed, check if there is
            # a package installed that provides this dependency
            # (e.g. scrollkeeper dependecies are provided by rarian-compat)
            # but only do that if there is no version required in the
            # dependency (we do not supprot versionized dependencies)
            if not oper:
                for ppkg in self._cache.get_providing_packages(
                    depname, include_nonvirtual=True):
                    if ppkg.is_installed:
                        self._dbg(3, "found installed '%s' that provides '%s'" % (ppkg.name, depname))
                        return True
        return False

    def _satisfy_or_group(self, or_group):
        """Try to satisfy the or_group."""
        for dep in or_group:
            depname, ver, oper = dep

            # multiarch
            depname = self._maybe_append_multiarch_suffix(depname)

            # if we don't have it in the cache, it may be virtual
            if not depname in self._cache:
                if not self._cache.is_virtual_package(depname):
                    continue
                providers = self._cache.get_providing_packages(depname)
                # if a package just has a single virtual provider, we
                # just pick that (just like apt)
                if len(providers) != 1:
                    continue
                depname = providers[0].name

            # now check if we can satisfy the deps with the candidate(s)
            # in the cache
            pkg = self._cache[depname]
            cand = self._cache._depcache.get_candidate_ver(pkg._pkg)
            if not cand:
                continue
            if not apt_pkg.check_dep(cand.ver_str, oper, ver):
                continue

            # check if we need to install it
            self._dbg(2, "Need to get: %s" % depname)
            self._need_pkgs.append(depname)
            return True

        # if we reach this point, we failed
        or_str = ""
        for dep in or_group:
            or_str += dep[0]
            if ver and oper:
                or_str += " (%s %s)" % (dep[2], dep[1])
            if dep != or_group[len(or_group)-1]:
                or_str += "|"
        self._failure_string += _("Dependency is not satisfiable: %s\n") % or_str
        return False

    def _check_single_pkg_conflict(self, pkgname, ver, oper):
        """Return True if a pkg conflicts with a real installed/marked pkg."""
        # FIXME: deal with conflicts against its own provides
        #        (e.g. Provides: ftp-server, Conflicts: ftp-server)
        self._dbg(3, "_check_single_pkg_conflict() pkg='%s' ver='%s' oper='%s'" % (pkgname, ver, oper))
        pkg = self._cache[pkgname]
        if pkg.is_installed:
            pkgver = pkg.installed.version
        elif pkg.marked_install:
            pkgver = pkg.candidate.version
        else:
            return False
        #print "pkg: %s" % pkgname
        #print "ver: %s" % ver
        #print "pkgver: %s " % pkgver
        #print "oper: %s " % oper
        if (apt_pkg.check_dep(pkgver, oper, ver) and not
            self.replaces_real_pkg(pkgname, oper, ver)):
            self._failure_string += _("Conflicts with the installed package "
                                      "'%s'") % pkg.name
            self._dbg(3, "conflicts with installed pkg '%s'" % pkg.name)
            return True
        return False

    def _check_conflicts_or_group(self, or_group):
        """Check the or-group for conflicts with installed pkgs."""
        self._dbg(2, "_check_conflicts_or_group(): %s " % (or_group))
        for dep in or_group:
            depname = dep[0]
            ver = dep[1]
            oper = dep[2]

            # FIXME: is this good enough? i.e. will apt always populate
            #        the cache with conflicting pkgnames for our arch?
            depname = self._maybe_append_multiarch_suffix(
                depname, in_conflict_checking=True)

            # check conflicts with virtual pkgs
            if not depname in self._cache:
                # FIXME: we have to check for virtual replaces here as
                #        well (to pass tests/gdebi-test8.deb)
                if self._cache.is_virtual_package(depname):
                    for pkg in self._cache.get_providing_packages(depname):
                        self._dbg(3, "conflicts virtual check: %s" % pkg.name)
                        # P/C/R on virtal pkg, e.g. ftpd
                        if self.pkgname == pkg.name:
                            self._dbg(3, "conflict on self, ignoring")
                            continue
                        if self._check_single_pkg_conflict(pkg.name, ver,
                                                           oper):
                            self._installed_conflicts.add(pkg.name)
                continue
            if self._check_single_pkg_conflict(depname, ver, oper):
                self._installed_conflicts.add(depname)
        return bool(self._installed_conflicts)

    @property
    def conflicts(self):
        """List of package names conflicting with this package."""
        key = "Conflicts"
        try:
            return apt_pkg.parse_depends(self._sections[key])
        except KeyError:
            return []

    @property
    def depends(self):
        """List of package names on which this package depends on."""
        depends = []
        # find depends
        for key in "Depends", "Pre-Depends":
            try:
                depends.extend(apt_pkg.parse_depends(self._sections[key]))
            except KeyError:
                pass
        return depends

    @property
    def provides(self):
        """List of virtual packages which are provided by this package."""
        key = "Provides"
        try:
            return apt_pkg.parse_depends(self._sections[key])
        except KeyError:
            return []

    @property
    def replaces(self):
        """List of packages which are replaced by this package."""
        key = "Replaces"
        try:
            return apt_pkg.parse_depends(self._sections[key])
        except KeyError:
            return []

    def check_conflicts(self):
        """Check if there are conflicts with existing or selected packages.

        Check if the package conflicts with a existing or to be installed
        package. Return True if the pkg is OK.
        """
        res = True
        for or_group in self.conflicts:
            if self._check_conflicts_or_group(or_group):
                #print "Conflicts with a exisiting pkg!"
                #self._failure_string = "Conflicts with a exisiting pkg!"
                res = False
        return res

    def check_breaks_existing_packages(self):
        """
        check if installing the package would break exsisting
        package on the system, e.g. system has:
        smc depends on smc-data (= 1.4)
        and user tries to installs smc-data 1.6
        """
        # show progress information as this step may take some time
        size = float(len(self._cache))
        steps = max(int(size/50), 1)
        debver = self._sections["Version"]
        debarch = self._sections["Architecture"]
        # store what we provide so that we can later check against that
        provides = [ x[0][0] for x in self.provides]
        for (i, pkg) in enumerate(self._cache):
            if i%steps == 0:
                self._cache.op_progress.update(float(i)/size*100.0)
            if not pkg.is_installed:
                continue
            # check if the exising dependencies are still satisfied
            # with the package
            ver = pkg._pkg.current_ver
            for dep_or in pkg.installed.dependencies:
                for dep in dep_or.or_dependencies:
                    if dep.name == self.pkgname:
                        if not apt_pkg.check_dep(debver, dep.relation, dep.version):
                            self._dbg(2, "would break (depends) %s" % pkg.name)
                            # TRANSLATORS: the first '%s' is the package that breaks, the second the dependency that makes it break, the third the relation (e.g. >=) and the latest the version for the releation
                            self._failure_string += _("Breaks existing package '%(pkgname)s' dependency %(depname)s (%(deprelation)s %(depversion)s)") % {
                                'pkgname' : pkg.name,
                                'depname' : dep.name,
                                'deprelation' : dep.relation,
                                'depversion' : dep.version}
                            self._cache.op_progress.done()
                            return False
            # now check if there are conflicts against this package on
            # the existing system
            if "Conflicts" in ver.depends_list:
                for conflicts_ver_list in ver.depends_list["Conflicts"]:
                    for c_or in conflicts_ver_list:
                        if c_or.target_pkg.name == self.pkgname and c_or.target_pkg.architecture == debarch:
                            if apt_pkg.check_dep(debver, c_or.comp_type, c_or.target_ver):
                                self._dbg(2, "would break (conflicts) %s" % pkg.name)
				# TRANSLATORS: the first '%s' is the package that conflicts, the second the packagename that it conflicts with (so the name of the deb the user tries to install), the third is the relation (e.g. >=) and the last is the version for the relation
                                self._failure_string += _("Breaks existing package '%(pkgname)s' conflict: %(targetpkg)s (%(comptype)s %(targetver)s)") % {
                                    'pkgname' : pkg.name,
                                    'targetpkg' : c_or.target_pkg.name,
                                    'comptype' : c_or.comp_type,
                                    'targetver' : c_or.target_ver }
                                self._cache.op_progress.done()
                                return False
                        if (c_or.target_pkg.name in provides and
                            self.pkgname != pkg.name):
                            self._dbg(2, "would break (conflicts) %s" % provides)
                            self._failure_string += _("Breaks existing package '%(pkgname)s' that conflict: '%(targetpkg)s'. But the '%(debfile)s' provides it via: '%(provides)s'") % {
                                'provides' : ",".join(provides),
                                'debfile'  : self.filename,
                                'targetpkg' : c_or.target_pkg.name,
                                'pkgname' : pkg.name }
                            self._cache.op_progress.done()
                            return False
        self._cache.op_progress.done()
        return True

    def compare_to_version_in_cache(self, use_installed=True):
        """Compare the package to the version available in the cache.

        Checks if the package is already installed or availabe in the cache
        and if so in what version, returns one of (VERSION_NONE,
        VERSION_OUTDATED, VERSION_SAME, VERSION_NEWER).
        """
        self._dbg(3, "compare_to_version_in_cache")
        pkgname = self._sections["Package"]
        debver = self._sections["Version"]
        self._dbg(1, "debver: %s" % debver)
        if pkgname in self._cache:
            if use_installed and self._cache[pkgname].installed:
                cachever = self._cache[pkgname].installed.version
            elif not use_installed and self._cache[pkgname].candidate:
                cachever = self._cache[pkgname].candidate.version
            else:
                return self.VERSION_NONE
            if cachever is not None:
                cmp = apt_pkg.version_compare(cachever, debver)
                self._dbg(1, "CompareVersion(debver,instver): %s" % cmp)
                if cmp == 0:
                    return self.VERSION_SAME
                elif cmp < 0:
                    return self.VERSION_NEWER
                elif cmp > 0:
                    return self.VERSION_OUTDATED
        return self.VERSION_NONE

    def depends_check(self):
        """Check package dependencies."""
        self._dbg(3, "check")

        self._check_was_run = True

        if not self._satisfy_depends(self.depends):
            return False


    def check(self):
        """Check if the package is installable."""
        self._dbg(3, "check")

        self._check_was_run = True

        # check arch
        if not "Architecture" in self._sections:
            self._dbg(1, "ERROR: no architecture field")
            self._failure_string = _("No Architecture field in the package")
            return False
        arch = self._sections["Architecture"]
        if  arch != "all" and arch != apt_pkg.config.find("APT::Architecture"):
            if arch in apt_pkg.get_architectures():
                self._multiarch = arch
                self.pkgname = "%s:%s" % (self.pkgname, self._multiarch)
                self._dbg(1, "Found multiarch arch: '%s'" % arch)
            else:
                self._dbg(1, "ERROR: Wrong architecture dude!")
                self._failure_string = _("Wrong architecture '%s'") % arch
                return False

        self._failure_string = ""

        if self._cache._depcache.broken_count > 0:
            self._failure_string = _("Failed to satisfy all dependencies "
                                     "(broken cache)")
            # clean the cache again
            self._cache.clear()
            return False
        return True

    def _satisfy_depends(self, depends):
        """Satisfy the dependencies."""
        # turn off MarkAndSweep via a action group (if available)
        try:
            _actiongroup = apt_pkg.ActionGroup(self._cache._depcache)
        except AttributeError:
            pass
        # check depends
        for or_group in depends:
            #print "or_group: %s" % or_group
            #print "or_group satified: %s" % self._is_or_group_satisfied(or_group)
            if not self._is_or_group_satisfied(or_group):
                if not self._satisfy_or_group(or_group):
                    return False
        # now try it out in the cache
        for pkg in self._need_pkgs:
            try:
                self._cache[pkg].mark_install(from_user=False)
            except SystemError:
                self._failure_string = _("Cannot install '%s'") % pkg
                self._cache.clear()
                return False
        return True

    @property
    def missing_deps(self):
        """Return missing dependencies."""
        self._dbg(1, "Installing: %s" % self._need_pkgs)
        if not self._check_was_run:
            raise AttributeError("property only available after depends_check() is ran")
        return self._need_pkgs

    @staticmethod
    def to_hex(in_data):
        hex = ""
        for (i, c) in enumerate(in_data):
            if i%80 == 0:
                hex += "\n"
            hex += "%2.2x " % ord(c)
        return hex

    @staticmethod
    def to_strish(in_data):
        s = ""
        # py2 compat, in_data is type string
        if type(in_data) == str:
            for c in in_data:
                if ord(c) < 10 or ord(c) > 127:
                    s += " "
                else:
                    s += c
        # py3 compat, in_data is type bytes
        else:
            for b in in_data:
                if b < 10 or b > 127:
                    s += " "
                else:
                    s += chr(b)
        return s

    def _get_content(self, part, name, auto_decompress=True, auto_hex=True):
        if name.startswith("./"):
            name = name[2:]
        data = part.extractdata(name)
        # check for zip content
        if name.endswith(".gz") and auto_decompress:
            io = StringIO(data)
            gz = gzip.GzipFile(fileobj=io)
            data = _("Automatically decompressed:\n\n")
            data += gz.read()
        # auto-convert to hex
        try:
            data = unicode(data, "utf-8")
        except Exception:
            new_data = _("Automatically converted to printable ascii:\n")
            new_data += self.to_strish(data)
            return new_data
        return data

    def _dbg(self, level, msg):
        """Write debugging output to sys.stderr."""
        if level <= self.debug:
            print >> sys.stderr, msg