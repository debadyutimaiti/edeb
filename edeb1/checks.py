import os
import string
import re
import logging
import gc
import evas, ecore, esudo
import elementary as elm
import debfile as debianfile
import urllib2, commands

"""eDeb Checks/Information Functions

Part of eDeb, a deb-package installer built on Python-EFL's.
By: AntCer (bodhidocs@gmail.com)

"""

logging.basicConfig(level=logging.DEBUG)
HOME = os.getenv("HOME")

#----Common
def popup_close(btn, popup):
    popup.delete()

def iw_close(bt, iw):
    iw.delete()
    gc.collect()

#----Popups
def nofile_error_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>No File Selected</><br><br>Please select an appropriate file candidate for installation."
    popup.timeout = 3.0
    popup.show()

def file_noexist_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>File does not exist</><br><br>Please select an appropriate file candidate for installation."
    popup.timeout = 3.0
    popup.show()

def file_error_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>Invalid File Format</><br><br>That is <em>not</> a .deb file!"
    popup.timeout = 3.0
    popup.show()

def no_net_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>Error</><br><br>No internet access.<br>Please try again when connected to internet."
    bt = elm.Button(win)
    bt.text = "OK"
    bt.callback_clicked_add(popup_close, popup)
    popup.part_content_set("button1", bt)
    popup.show()

def finished_dep_install_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>Successful!</b><br><br>Missing dependencies successfully installed."
    bt = elm.Button(win)
    bt.text = "OK"
    bt.callback_clicked_add(popup_close, popup)
    popup.part_content_set("button1", bt)
    popup.show()

def not_installable_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>Error</b><br><br>This file has failed initial check. It cannot be installed.<br><br>This is most often caused by a previously broken installation. Click <b>Fix</b> to attempt to repair broken packages, then try again.<br><br>If this occurs again, then the file may be of the wrong architecture."
    bt = elm.Button(win)
    bt.text = "Fix"
    bt.callback_clicked_add(dependency_comp, popup, win)
    popup.part_content_set("button1", bt)
    bt = elm.Button(win)
    bt.text = "Close"
    bt.callback_clicked_add(popup_close, popup)
    popup.part_content_set("button2", bt)
    popup.show()

def dependency_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>Urgent</b><br><br>Installation Semi-Finished. All dependencies were not met.<ps><ps>Click <b>Grab</> to attempt to grab the missing dependencies and complete the installation."
    bt = elm.Button(win)
    bt.text = "Grab"
    bt.callback_clicked_add(dependency_comp, popup, win)
    popup.part_content_set("button1", bt)
    popup.show()

def finished_popup(win):
    popup = elm.Popup(win)
    popup.size_hint_weight = (1.0, 1.0)
    popup.text = "<b>Installation Finished!</b><br><br>The installation was successful."
    bt = elm.Button(win)
    bt.text = "OK"
    bt.callback_clicked_add(popup_close, popup)
    popup.part_content_set("button1", bt)
    popup.show()

#----Dependency Completion
def dependency_comp(bt, popup, win):
    popup.delete()
    try:
        con = urllib2.urlopen("http://www.google.com/")
    except:
        logging.exception("No network activity detected")
        logging.exception("Please try again with an established Internet Connection.")
        no_net_popup(win)
    else:
        logging.info("Starting attempt to fulfill dependencies:")
        dep_comp = "apt-get -f install -y"
        n = elm.Notify(win)
        esudo.eSudo(dep_comp, win, start_callback=start_cb, end_callback=dep_cb, data=n)

#---End Callbacks
def dep_grab_cb(exit_code, win, *args, **kwargs):
    n = kwargs["data"]
    n.delete()
    if exit_code == 0:
        logging.info("Successfully Grabbed Dependencies.")
        finished_dep_install_popup(win)
        gc.collect()
    else:
        logging.info("Something went wrong while installing dependencies.")
def main_cb(exit_code, win, bt1, bt2, en, *args, **kwargs):
    n = kwargs["data"]
    n.delete()
    bt1.disabled_set(False)
    bt2.disabled_set(False)
    en.disabled_set(False)
    if exit_code == 0:
        logging.info("Installation Completed!")
        finished_popup(win)
        gc.collect()
    else:
        logging.info("Something went wrong. Likely, dependencies that weren't met before attempting installation.")
        dependency_popup(win)
def dep_cb(exit_code, win, *args, **kwargs):
    n = kwargs["data"]
    n.delete()
    if exit_code == 0:
        logging.info("Successfully Grabbed Dependencies & Completed Installation.")
        finished_popup(win)
        gc.collect()
    else:
        logging.info("Something went wrong while attempting to complete installation.")

#---Start Callback
def start_cb(win, *args, **kwargs):
    n = kwargs["data"]

    box = elm.Box(win)
    box.size_hint_weight = 1.0, 1.0
    box.size_hint_align = -1.0, -1.0

    lb = elm.Label(win)
    lb.text = "<b>Please wait...</b>"
    lb.size_hint_align = 0.0, 0.5
    box.pack_end(lb)
    lb.show()

    sep = elm.Separator(win)
    sep.horizontal = True
    box.pack_end(sep)
    sep.show()

    pb = elm.Progressbar(win)
    pb.style = "wheel"
    pb.pulse(True)
    pb.size_hint_weight = 1.0, 1.0
    pb.size_hint_align_set(-1.0, -1.0)
    box.pack_end(pb)
    pb.show()

    box.show()

    n.orient = 1
    n.allow_events_set(False)
    n.content = box
    n.show()





class Checks(object):
    def __init__(self, command=False, window=False, end_callback=False ):
        self.win = window
        self.file = command
        self.depbtn = depbtn = False
        self.depcheck = depcheck = False
        self.end_cb = end_callback if callable(end_callback) else None

#----Package Info
    def pkg_information(self, win):
        deb = debianfile.DebPackage(self.file, cache=None)
#----------------Desc
        long_desc = ""
        raw_desc = string.split(deb["Description"], "\n")
        # append a newline to the summary in the first line
        summary = raw_desc[0]
        raw_desc[0] = ""
        long_desc = "%s\n" % summary
        for line in raw_desc:
            tmp = string.strip(line)
            long_desc += tmp + "\n"
        # do some regular expression magic on the description
        # Add a newline before each bullet
        p = re.compile(r'^(\s|\t)*(\*|0|-)',re.MULTILINE)
        long_desc = p.sub('\n*', long_desc)
        p = re.compile(r'\n', re.MULTILINE)
        long_desc = p.sub(" ", long_desc)
        p = re.compile(r'\s\s+', re.MULTILINE)
        summary = p.sub("<br>", long_desc)
        long_desc = "<br><b>Description:</> %s<br>" % summary
        pkg_desc = long_desc
#----------------Name
        long_desc = ""
        raw_desc = string.split(deb["Package"], "\n")
        summary = raw_desc[0]
        long_desc = "<b>Package:</> %s" % summary
        pkg_name = long_desc
#----------------Auth
        long_desc = ""
        raw_desc = string.split(deb["Maintainer"], "\n")
        summary = raw_desc[0]
        long_desc = "<b>Maintainer:</> %s" % summary
        pkg_auth = long_desc
#----------------Ver
        long_desc = ""
        raw_desc = string.split(deb["Version"], "\n")
        summary = raw_desc[0]
        long_desc = "<b>Version:</> %s" % summary
        pkg_ver = long_desc
#----------------Arch
        long_desc = ""
        raw_desc = string.split(deb["Architecture"], "\n")
        summary = raw_desc[0]
        long_desc = "<b>Architecture:</> %s" % summary
        pkg_arch = long_desc
#----------------Sec
        long_desc = ""
        raw_desc = string.split(deb["Section"], "\n")
        summary = raw_desc[0]
        long_desc = "<b>Section:</> %s" % summary
        pkg_sec = long_desc
#----------------Pri
        long_desc = ""
        raw_desc = string.split(deb["Priority"], "\n")
        summary = raw_desc[0]
        long_desc = "<b>Priority:</> %s" % summary
        pkg_pri = long_desc
#----------------Size
        try:
            deb["Installed-Size"]
            long_desc = ""
            raw_desc = string.split(deb["Installed-Size"] + " KB", "\n")
            summary = raw_desc[0]
            long_desc = "<b>Installed-Size:</> %s<ps>" % summary
            pkg_size = long_desc
        except:
            pkg_size = ""
#----------------Recc
        try:
            deb["Recommends"]
            long_desc = ""
            raw_desc = string.split(deb["Recommends"], "\n")
            summary = raw_desc[0]
            long_desc = "<b>Recommends:</> %s<ps>" % summary
            pkg_recc = long_desc
        except:
            pkg_recc = ""
#----------------Conf
        try:
            deb["Conflicts"]
            long_desc = ""
            raw_desc = string.split(deb["Conflicts"], "\n")
            summary = raw_desc[0]
            long_desc = "<b>Conflicts:</> %s<ps>" % summary
            pkg_conf = long_desc
        except:
            pkg_conf = ""
#----------------Repl
        try:
            deb["Replaces"]
            long_desc = ""
            raw_desc = string.split(deb["Replaces"], "\n")
            summary = raw_desc[0]
            long_desc = "<b>Replaces:</> %s<ps>" % summary
            pkg_repl = long_desc
        except:
            pkg_repl = ""
#----------------Prov
        try:
            deb["Provides"]
            long_desc = ""
            raw_desc = string.split(deb["Provides"], "\n")
            summary = raw_desc[0]
            long_desc = "<b>Provides:</> %s<ps>" % summary
            pkg_prov = long_desc
        except:
            pkg_prov = ""
#----------------HP
        try:
            deb["Homepage"]
            long_desc = ""
            raw_desc = string.split(deb["Homepage"], "\n")
            summary = raw_desc[0]
            long_desc = "<b>Homepage:</> %s" % summary
            pkg_hp = long_desc
        except:
            pkg_hp = ""
#----------------Dep
        pkg_dep  = commands.getoutput("dpkg -f %s | sed 's/<</less than/' | awk '/Depends:/' | sed 's/Depends:/ /' | sed 's/Pre-/ /'" %self.file)
#----------------FB
        if pkg_hp == "" and pkg_size == "" and pkg_recc == "" and pkg_prov == "" and pkg_conf == "" and pkg_repl == "":
            pkg_size = "None<ps>"


        def dependency_grab(tb, bt, win):
            try:
                con = urllib2.urlopen("http://www.google.com/")
            except:
                logging.exception("No network activity detected")
                logging.exception("Please try again with an established Internet Connection.")
                iw.delete()
                no_net_popup(win)
            else:
                missingdep = deb.missing_deps
                separator_string = " "
                missdep = separator_string.join(missingdep)
                logging.info("Starting Dependency Grab:")
                dep_grab = "apt-get --no-install-recommends install -y %s" %(missdep)
                n = elm.Notify(win)
                esudo.eSudo(dep_grab, win, start_callback=start_cb, end_callback=dep_grab_cb, data=n)

        def compare(tb, btn, pkg_info_en):
            debcompare = deb.compare_to_version_in_cache(use_installed=True)
            debcomparerepo = deb.compare_to_version_in_cache(use_installed=False)
            pkg_info_en.entry_set("<b>Installed Version<ps>")
            if debcompare == 1:
                pkg_info_en.entry_append("Outdated:</b> This version is lower than the version currently installed.")
            elif debcompare == 2:
                pkg_info_en.entry_append("Same:</b> The same version is already installed.")
            elif debcompare == 3:
                pkg_info_en.entry_append("Newer:</b> This version is higher than the version currently installed.")
            elif debcompare == 0:
                pkg_info_en.entry_append("None:</b> This application has not been installed.")
            else:
                pkg_info_en.entry_append("Not found:</b> A version installed or in the repository cannot be located for comparison.")

            pkg_info_en.entry_append("<ps><ps><b>Repository Version<ps>")
            if debcomparerepo == 1:
                pkg_info_en.entry_append("Outdated:</b> This version is lower than the version available in the repository.")
            elif debcomparerepo == 2:
                pkg_info_en.entry_append("Same:</b> This version is the same as the version available in the repository.")
            elif debcomparerepo == 3:
                pkg_info_en.entry_append("Newer:</b> This version is higher than the version available in the repository.")
            elif debcomparerepo == 0:
                pkg_info_en.entry_append("None:</b> This application cannot be located in the repository.")
            else:
                pkg_info_en.entry_append("Not found:</b> A version installed or in the repository cannot be located for comparison.")

        def checks(tb, btn, pkg_info_en):
            btn.disabled_set(True)
            def real_checks(btn, pkg_info_en):
                if deb.check_breaks_existing_packages() == False:
                    pkg_info_en.entry_set("<b>WARNING:</> Installing this package will <b>BREAK</> certain existing packages.")
                elif deb.check_conflicts() == False:
                    pkg_info_en.entry_set("<b>WARNING:</> There are conflicting packages!")
                    conflicting = deb.conflicts
                    pkg_info_en.entry_append("<ps> %s" %conflicting)
                else:
                    pkg_info_en.entry_set("<b>CLEAR:</> You are cleared to go. The selected file has passed <b>ALL</> checks.")
                btn.disabled_set(False)
            et = ecore.Timer(0.3, real_checks, btn, pkg_info_en)
            pkg_info_en.entry_set("<b>Please wait...</>")

        def depends(tb, btn, pkg_info_en):
            if self.depcheck:
                pass
            else:
                self.depcheck = True
                deb.depends_check()
            missingdep = deb.missing_deps
            separator_string = " , "
            missdep = separator_string.join(missingdep)
            pkg_info_en.entry_set("<b>Dependencies:</> %s<ps><ps><b>Missing Dependencies:</> " %pkg_dep)
            if missingdep == []:
                pkg_info_en.entry_append("None<ps>")
            else:
                pkg_info_en.entry_append("%s<ps>" %missdep)
                if self.depbtn:
                    return
                else:
                    tb = elm.Toolbar(self.win)
                    tb.size_hint_weight_set(1.0, 0.0)
                    tb.size_hint_align_set(-1.0, -1.0)
                    tb.item_append("", "Attempt to Install Missing Dependencies", dependency_grab, self.win)
                    tb.select_mode_set(2)
                    pkgbox.pack_end(tb)
                    tb.show()
                    self.depbtn = True
                    return

        def info(tb, btn, pkg_info_en):
            pkg_info_en.entry_set("%s<ps>%s<ps>%s<ps>%s<ps>%s<ps>%s<ps>%s<ps><ps><b><i>Extra Information:</i></b><ps>%s%s%s%s%s%s" \
                            %(pkg_name, pkg_auth, pkg_ver, pkg_arch, pkg_sec, pkg_pri, pkg_desc, pkg_size, pkg_recc, pkg_conf, pkg_repl, pkg_prov, pkg_hp))

        def files(tb, btn, pkg_info_en):
            btn.disabled_set(True)
            def real_files(btn, pkg_info_en):
                filestosort = deb.filelist
                separator_string = "<br>"
                filesinlist = separator_string.join(filestosort)
                pkg_info_en.entry_set("<b>Files:</><ps>%s<ps>" %filesinlist)
                btn.disabled_set(False)
            et = ecore.Timer(0.3, real_files, btn, pkg_info_en)
            pkg_info_en.entry_set("<b>Loading file list...</>")

        def closebtn(tb, btn, iw):
            self.depbtn = None
            self.depcheck = None
            iw_close(btn, iw)


        pkgbox = elm.Box(self.win)
        pkgbox.size_hint_weight_set(1.0, 1.0)

        pkgfr = elm.Frame(self.win)
        pkgfr.text_set("Package Information")
        pkgbox.pack_end(pkgfr)

        pkg_info_en = elm.Entry(self.win)
        pkg_info_en.line_wrap_set(2)
        pkg_info_en.input_panel_return_key_disabled = False
        pkg_info_en.size_hint_align_set(-1.0, -1.0)
        pkg_info_en.size_hint_weight_set(1.0, 1.0)
        pkg_info_en.editable_set(False)
        pkg_info_en.scrollable_set(True)
        pkg_info_en.entry_set("%s<ps>%s<ps>%s<ps>%s<ps>%s<ps>%s<ps>%s<ps><ps><b><i>Extra Information:</i></b><ps>%s%s%s%s%s%s" \
                            %(pkg_name, pkg_auth, pkg_ver, pkg_arch, pkg_sec, pkg_pri, pkg_desc, pkg_size, pkg_recc, pkg_conf, pkg_repl, pkg_prov, pkg_hp))

        pkgbox.pack_end(pkg_info_en)
        pkg_info_en.show()

        pkgbox.show()
        pkgfr.show()

        iw = elm.InnerWindow(self.win)
        iw.content_set(pkgbox)
        iw.show()
        iw.activate()

        btnbox = elm.Box(self.win)
        btnbox.horizontal = True
        btnbox.size_hint_weight = (1.0, 0.0)
        pkgbox.pack_end(btnbox)
        btnbox.show()

        tb = elm.Toolbar(self.win)
        tb.size_hint_weight_set(1.0, 0.0)
        tb.size_hint_align_set(-1.0, -1.0)
        tb.item_append("", "Info", info, pkg_info_en)
        tb.item_append("", "Compare", compare, pkg_info_en)
        tb.item_append("", "Checks", checks, pkg_info_en)
        tb.item_append("", "Depends", depends, pkg_info_en)
        tb.item_append("", "Files", files, pkg_info_en)
        tb.homogeneous_set(True)
        tb.select_mode_set(2)
        btnbox.pack_end(tb)
        tb.show()

        tb = elm.Toolbar(self.win)
        tb.size_hint_weight_set(1.0, 0.0)
        tb.size_hint_align_set(-1.0, -1.0)
        tb.item_append("", "OK", closebtn, iw)
        tb.select_mode_set(2)
        pkgbox.pack_end(tb)
        tb.show()

#----Checks
    def check_file(self, fs, win):
        if self.file == HOME:
            nofile_error_popup(win)
            return
        else:
            self.pkg_information(self)
            return

    def check_file_install(self, bt1, win, bt2, en):
        if self.file == HOME:
            nofile_error_popup(win)
            return
        else:
            bt1.disabled_set(True)
            bt2.disabled_set(True)
            en.disabled_set(True)
            self.bt1 = bt1
            self.bt2 = bt2
            logging.info("Package: %s" %self.file)
            install_deb = 'dpkg -i %s'%self.file
            n = elm.Notify(win)
            esudo.eSudo(install_deb, win, bt1, bt2, en, start_callback=start_cb, end_callback=main_cb, data=n)
            return
