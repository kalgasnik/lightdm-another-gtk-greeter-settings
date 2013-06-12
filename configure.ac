#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_INIT([lightdm-another-gtk-greeter-settings], [1.0.0], [pan.pav.7c5@gmail.com])

AM_INIT_AUTOMAKE
AM_PATH_PYTHON([3.0])

IT_PROG_INTLTOOL(0.35.0)

AC_SUBST(GETTEXT_PACKAGE, lightdm-another-gtk-greeter-settings)
AC_DEFINE_UNQUOTED(GETTEXT_PACKAGE, "$GETTEXT_PACKAGE", Gettext package)

GETTEXT_DIR=[${datadir}/locale]
AC_SUBST(GETTEXT_DIR)

AC_CONFIG_FILES([
	Makefile
	src/Makefile
	src/application/Makefile
	data/Makefile
	po/Makefile.in])

AC_OUTPUT