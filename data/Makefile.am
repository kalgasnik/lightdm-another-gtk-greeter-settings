interfacedir = $(datadir)/lightdm-another-gtk-greeter-settings
dist_interface_DATA = interface.ui

desktopdir = $(datadir)/applications
desktop_in_files = lightdm-another-gtk-greeter-settings.desktop.in
desktop_DATA = lightdm-another-gtk-greeter-settings.desktop
@INTLTOOL_DESKTOP_RULE@

EXTRA_DIST = $(desktop_in_files)

UPDATE_DESKTOP = update-desktop-database $(datadir)/applications || :

install-data-hook: 
	$(UPDATE_DESKTOP)
uninstall-hook: 
	$(UPDATE_DESKTOP)

