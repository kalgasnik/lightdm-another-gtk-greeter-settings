SUBDIRS = application

bin_SCRIPTS = lightdm-another-gtk-greeter-settings
CLEANFILES = $(bin_SCRIPTS)
EXTRA_DIST = lightdm-another-gtk-greeter-settings.in

do_subst = sed -e 's|@srcdir[@]|$(datadir)/lightdm-another-gtk-greeter-settings/src|g' \
               -e 's|@greeterconfig[@]|$(sysconfdir)/lightdm/lightdm-another-gtk-greeter.conf|g' \
               -e 's|@localedir[@]|$(GETTEXT_DIR)|g' \
               -e 's|@localedomain[@]|$(GETTEXT_PACKAGE)|g' \
               -e 's|@uifile[@]|$(datadir)/lightdm-another-gtk-greeter-settings/interface.ui|g'

lightdm-another-gtk-greeter-settings: lightdm-another-gtk-greeter-settings.in Makefile
	$(AM_V_GEN) $(do_subst) $< > $@
	chmod +x $@

