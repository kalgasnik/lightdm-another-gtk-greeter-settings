#!/usr/bin/python3

import argparse
import configparser
import os

from collections import namedtuple, Mapping
from itertools import chain, islice
from gi.repository import Gdk, Pango

import gettext
import locale
_ = gettext.gettext


__all__ = ['main']

def to_bool(s):
    return s.lower() in {'1', 'true', 'yes', 'on', 'enabled'} if type(s) is str else bool(s)

BindingTuple = namedtuple('BindingTuple', ('widget', 'signal', 'handler', 'change'))

def block_signals(widgets, f, *args, **kwargs):
    for widget, signal, handler, block in widgets:  # @UnusedVariable
        if block: widget.handler_block_by_func(handler)
    result = f(*args, **kwargs)
    for widget, signal, handler, block in widgets:  # @UnusedVariable
        if block: widget.handler_unblock_by_func(handler)
    return result

def block_default_signals(f):
    def _block_signals(self, *args, **kwargs):
        return block_signals(self._signals, f, self, *args, **kwargs) \
               if hasattr(self, '_signals') else f(self, *args, **kwargs)
    return _block_signals

class OptionWrapper:
    # Special fields:
    # WidgetsTuple(namedtuple) >>> self._widgets (name->widget)
    # WidgetsBinding: list of BindingTuple-like items, where widget and handler are names, not objects
    #                 >>> self._signals: list of BindingTuple with corresponded objects

    def __init__(self, default, widgets, prefs):
        self._changed = False
        self._enabled = True
        self._label = widgets.pop('label', None)
        self._widgets = widgets
        self._default = default
        self._prefs = prefs
        if hasattr(self, 'WidgetsTuple'):
            self._widget = self.WidgetsTuple._make(widgets.get(field, None) for field in self.WidgetsTuple._fields)
        else:
            self._widget = widgets.get('', None)
        self._bind()
    def __repr__(self):
        return self.__class__.__name__ + '(enabled: {_enabled}, changed: {_changed})'.format_map(self.__dict__)
    def _bind(self):
        if self._label:
            self._label.connect('toggled', self._on_label_toggled)
        if hasattr(self, 'WidgetsBinding'):
            self._signals = tuple(BindingTuple(self._widgets[name], signal,
                                              getattr(self, handler) if handler else self._on_change,
                                              (not handler and not block) or (block and block[0]))
                                 for name, signal, handler, *block in self.WidgetsBinding)
            for widget, signal, handler, block in self._signals:
                widget.connect(signal, handler)
    def _on_change(self, *args, **kwargs):
        self.touch()
    def _on_label_toggled(self, widget):
        self._set_enabled(self._label.props.active, True)
        self.touch()
    def reset(self):
        self.value = self._default
        self._changed = False
        if self._label:
            self._label.modify_font(Pango.FontDescription('normal'))
    def touch(self):
        self._changed = True
        if self._label:
            self._label.modify_font(Pango.FontDescription('bold'))
    def _get_widget_value(self):
        raise NotImplementedError()
    def _set_widget_value(self, value):
        raise NotImplementedError()
    def _set_enabled(self, value, block=False):
        self._enabled = value
        for w in filter(lambda w: isinstance(w, Gtk.Widget), self._widgets.values()):
            w.props.sensitive = value
        if not block and self._label:
            block_signals(((self._label, '', self._on_label_toggled, True),), self.label.set_active, value)
    @property
    def value(self):
        return self._get_widget_value()
    @value.setter
    @block_default_signals
    def value(self, value):
        self._set_widget_value(value)
    @property
    def default(self):
        return self._default
    @default.setter
    def default(self, value):
        self._default = value
    @property
    def changed(self):
        return self._changed
    @property
    def enabled(self):
        return self._enabled
    @enabled.setter
    def enabled(self, value):
        self._set_enabled(value)
    @property
    def label(self):
        return self._label


class BooleanOption(OptionWrapper):
    WidgetsBinding = ('', 'toggled', ''),
    def _on_notify_active_signal(self, widget, param, *args):
        if param.name == 'active':
            super()._on_change()
    def _bind(self):
        if isinstance(self._widget, Gtk.Switch):
            self.WidgetsBinding = ('', 'notify', '_on_notify_active_signal', True),
        super()._bind()
    def _set_widget_value(self, value):
        self._widget.props.active = to_bool(value)
    def _get_widget_value(self):
        return int(self._widget.props.active)

class StringOption(OptionWrapper):
    WidgetsBinding = ('', 'changed', ''),
    def _set_widget_value(self, value):
        self._widget.props.text = value
    def _get_widget_value(self):
        return self._widget.props.text

class IntegerOption(StringOption):
    def _set_widget_value(self, value):
        return super()._set_widget_value(str(value))
    def _get_widget_value(self):
        return int(super()._get_widget_value())

class ChoiceOption(OptionWrapper):
    def __init__(self, *args):
        super().__init__(*args)
        self._choices = {int(name.partition('_')[-1]): widget
                         for (name, widget) in self._widgets.items() if name.starts_with('choice_')}
        if not self._choices:
            self._choices = self._widget
    def _bind(self):
        super()._bind()
    def _set_widget_value(self, value):
        raise NotImplementedError()
    def _get_widget_value(self):
        raise NotImplementedError()

class FontOption(OptionWrapper):
    WidgetsBinding = ('', 'font-set', ''),
    def _set_widget_value(self, value):
        self._widget.props.font_name = value
    def _get_widget_value(self):
        return self._widget.get_font_name()

class PathOption(OptionWrapper):
    WidgetsBinding = ('', 'file-set', ''),
    def _set_widget_value(self, value):
        if not value:
            self._widget.unselect_all()
        else:
            if not os.path.isabs(value):
                value = os.path.abspath(os.path.join(self._prefs.get('current_dir', ''), value))
            self._widget.select_filename(value)
    def _get_widget_value(self):
        filename = self._widget.get_filename()
        relative = os.path.relpath(filename, self._prefs.get('current_dir', ''))
        return filename if relative.startswith('..') else relative

class BackgroundOption(OptionWrapper):
    WidgetsTuple = namedtuple('WidgetsTuple', ('file', 'color', 'is_file', 'is_color'))
    WidgetsBinding = ('file', 'file-set', '_on_file_changed'), ('color', 'color-set', '_on_color_changed'), ('is_file', 'toggled', ''),
    def _set_widget_value(self, value):
        is_file = not value.startswith('#')
        self._widget.is_file.props.active = is_file
        self._widget.is_color.props.active = not is_file
        if not value or not is_file:
            self._widget.file.unselect_all()
        if is_file:
            self._widget.file.select_filename(value)
        else:
            try:
                int(value[1:], 16)
            except ValueError:
                value = value[1:]
            try:
                color = Gdk.color_parse(value)
            except ValueError:
                pass
            else:
                self._widget.color.props.color = color
    def _get_widget_value(self):
        if self._widget.is_file.props.active:
            return self._widget.file.get_filename()
        else:
            return self._widget.color.props.color.to_string()
    def _on_color_changed(self, *args):
        self._widget.is_color.props.active = True
        self.touch()
    def _on_file_changed(self, *args):
        self._widget.is_file.props.active = True
        self.touch()

class IconOption(OptionWrapper):
    WidgetsTuple = namedtuple('WidgetsTuple', ('file', 'icon', 'is_file', 'is_icon'))
    WidgetsBinding = ('file', 'file-set', '_on_file_changed'), ('icon', 'changed', '_on_icon_changed'), ('is_file', 'toggled', ''),
    def _set_widget_value(self, value):
        is_file = not value.startswith('#')
        self._widget.is_file.props.active = is_file
        self._widget.is_icon.props.active = not is_file
        if not value or not is_file:
            self._widget.file.unselect_all()
        if is_file:
            self._widget.file.select_filename(value)
        else:
            self._widget.icon.props.text = value[1:]
    def _get_widget_value(self):
        if self._widget.is_file.props.active:
            return self._widget.file.get_filename()
        else:
            return ('#' + self._widget.icon.props.text) if self._widget.icon.props.text else ''
    def _on_icon_changed(self, *args):
        self._widget.is_icon.props.active = True
        self.touch()
    def _on_file_changed(self, *args):
        self._widget.is_file.props.active = True
        self.touch()

class FontScaleOption(OptionWrapper):
    WidgetsTuple = namedtuple('WidgetsTuple', ('scale', 'use', 'disabled'))
    WidgetsBinding = ('use', 'toggled', ''), ('scale', 'changed', '',)
    def _set_widget_value(self, value):
        self._widget.use.props.active = bool(value)
        self._widget.disabled.props.active = not bool(value)
        if value:
            self._widget.scale.props.text = value
    def _get_widget_value(self):
        return float(self._widget.scale.props.text) if self._widget.use.props.active else ''

class OSKOption(OptionWrapper):
    WidgetsTuple = namedtuple('WidgetsTuple', ('use_onboard', 'use_command', 'command'))
    WidgetsBinding = ('use_onboard', 'toggled', ''), ('command', 'changed', '',)
    def _set_widget_value(self, value):
        use_onboard = value == '#onboard'
        self._widget.use_onboard.props.active = use_onboard
        self._widget.use_command.props.active = not use_onboard
        self._widget.command.props.text = value if not use_onboard else ''
    def _get_widget_value(self):
        return '#onboard' if self._widget.use_onboard.props.active else self._widget.command.props.text

class IndicatorOption(OptionWrapper):
    class Model:
        NAME = 0
        DISPLAY_NAME = 1
        ENABLED = 3
        INCONSISTENT = 4
        PAGE = 5
    WidgetsBinding = ('', 'row-changed', '_on_row_changed'), ('toggle', 'toggled', '_on_toggled')
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._row = next(row for row in self._widget
                         if row[self.Model.NAME] == self._prefs['page'])
    def _on_row_changed(self, model, path, it):
        if model[it] == self._row:
            self.touch()
    def _on_toggled(self, toggle, path):
        if str(self._row.path) != path:
            return
        state = (self._row[self.Model.ENABLED] * 1 + self._row[self.Model.INCONSISTENT] * 2 + 1) % 3
        self._row[self.Model.ENABLED] = state % 2
        self._row[self.Model.INCONSISTENT] = state > 1
        self._enabled = state < 2
        if state > 1:
            self._changed = False
        else:
            self.touch()
    def _set_enabled(self, value, *args, **kwargs):
        super()._set_enabled(value, *args, **kwargs)
        self._row[self.Model.INCONSISTENT] = not value
    def _set_widget_value(self, value):
        self._row[self.Model.ENABLED] = to_bool(value)
    def _get_widget_value(self):
        return int(self._row[self.Model.ENABLED])


INDICATOR_WIDGETS = {'': '/indicators_model', 'toggle': '/indicators_renderer_toggle'}

class OPTION_INDEX:
    DEFAULT = 1

OPTIONS = \
{
    # 'section': {'key': (OptionWrapperClass, default_value, widgets, preferences), ...}
    'appearance': \
    {
        'theme-name': (StringOption, 'default'),
        'icon-theme-name': (StringOption, 'default'),
        'background': (BackgroundOption, ''),
        'ui-file': (PathOption, '', (), {'current_dir': '{greeter-data}'}),
        'css-file': (PathOption, '', (), {'current_dir': '{greeter-data}'}),
        'logo': (IconOption, ''),
        'font-name': (FontOption, ''),
        # 'fixed-user-image-size': (BooleanOption, True),
        # 'list-view-image-size': (IntegerOption, 48),
        'xft-dpi': (IntegerOption, 96),
        'date-format': (StringOption, '')
    },
    'greeter': \
    {
        'allow-other-users': (BooleanOption, False),
        'show-language-selector': (BooleanOption, True),
        'show-session-icon': (BooleanOption, False),
    },
    'panel': \
    {
        'show-panel': (BooleanOption, True),
        'panel-at-top': (BooleanOption, True, ('panel-at-bottom',)),
    },
    'clock': \
    {
        'enabled': (IndicatorOption, True, INDICATOR_WIDGETS, {'page': 'clock'}),
        'date-format': (StringOption, ''),
        'time-format': (StringOption, ''),
        'show-calendar': (BooleanOption, True),
    },
    'layout': \
    {
        'enabled': (IndicatorOption, True, INDICATOR_WIDGETS, {'page': 'layout'}),
    },
    'power': \
    {
        'enabled': (IndicatorOption, True, INDICATOR_WIDGETS, {'page': 'power'}),
        'suspend-prompt': (BooleanOption, True),
        'hibernate-prompt': (BooleanOption, True),
        'restart-prompt': (BooleanOption, True),
        'shutdown-prompt': (BooleanOption, True),
    },
    'a11y': \
    {
        'enabled': (IndicatorOption, False, INDICATOR_WIDGETS, {'page': 'a11y'}),
        'theme-name-contrast': (StringOption, ''),
        'icon-theme-name-contrast': (StringOption, ''),
        'font-scale': (FontScaleOption, '1.2'),
        'osk': (OSKOption, '#onboard'),
    }
}

class Application:
    OptionPath = namedtuple('OptionPath', ('section', 'key'))
    def __init__(self, prefs):
        if not prefs['greeter-config-output']:
            prefs['greeter-config-output'] = prefs['greeter-config']
        if not os.path.isabs(prefs['ui-file']):
            prefs['ui-file'] = os.path.join(os.path.abspath(os.curdir), prefs['ui-file'])
        self.prefs = prefs
        self.config = None
        self.gui = self.create_gui()

        # Option -> (section, key)
        self.options = {self.create_option(section, key, args): self.OptionPath(section, key)
                        for section, keys in OPTIONS.items()
                            for key, args in keys.items()}

        self.__dict__.update((name, self.gui[name]) for name in
                             ('main_window', 'label_menu', 'label_menu_reset',
                              'indicators_model', 'indicators_selection', 'indicators_notebook'))

        for row in self.indicators_model:
            page = self.gui['indicator_page_{name}'.format(name=row[IndicatorOption.Model.NAME])]
            row[IndicatorOption.Model.PAGE] = self.indicators_notebook.page_num(page) if page else 0
        self.indicators_selection.select_path('0')

    def create_option(self, section, key, args):
        klass, default, widgets_names, prefs = chain(args, islice((None, None, (), {}), len(args), None))

        widgets = {'': '', 'label': 'label'}
        if hasattr(klass, 'WidgetsTuple'):
            widgets.update((name, name) for name in klass.WidgetsTuple._fields)
        if isinstance(widgets_names, Mapping):
            widgets.update(widgets_names)
        elif widgets_names:
            widgets.update((name.lstrip('/'), name) for name in widgets_names)
        widgets = {name: self.gui['_'.join(filter(None, (section, key, widget)))]
                         if not widget.startswith('/') else self.gui[widget[1:]]
                         for name, widget in widgets.items()}
        prefs.update((k, v.format_map(self.prefs)) for k, v in prefs.items() if type(v) is str)
        option = klass(default, widgets, prefs)
        if option.label:
            option.label.connect('button-press-event', self._on_label_click, option)
        return option

    def create_gui(self):
        builder = Gtk.Builder()
        if 'localedomain' in self.prefs:
            builder.set_translation_domain(self.prefs['localedomain'])
        builder.add_from_file(self.prefs['ui-file'])
        builder.connect_signals(self)
        class BuilderWrapper:
            def __init__(self, builder):
                self._builder = builder
            def __getitem__(self, key):
                return self._builder.get_object(key)
        return BuilderWrapper(builder)

    def run(self):
        self.read()
        Gtk.main()

    def read(self):
        self.config = configparser.ConfigParser(allow_no_value=True)
        try:
            self.config.read(self.prefs['greeter-config'])
        except configparser.Error as e:
            self.show_error(e)

        for option, (section, key) in self.options.items():
            option.enabled = self.config.has_option(section, key)
            option.default = self.config[section][key] if option.enabled else OPTIONS[section][key][OPTION_INDEX.DEFAULT]
            option.reset()

    def save(self):
        diff = ((o, p) for o, p in self.options.items() if o.changed)
        for option, (section, key) in diff:
            if option.enabled:
                if not self.config.has_section(section):
                    self.config.add_section(section)
                self.config.set(section, key, str(option.value))
            else:
                self.config.remove_option(section, key)

        sections_to_delete = [s for s in self.config if s != 'DEFAULT' and not self.config[s]]
        for section in sections_to_delete:
            del self.config[section]

        try:
            with open(self.prefs['greeter-config-output'], mode='w') as file:
                self.config.write(file)
        except OSError as e:
            self.show_error(e)
            return False
        return True

    def show_error(self, error):
        dialog = Gtk.MessageDialog(self.gui['main_window'], message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK,
                                   title='Error occurred', message_format=str(error))
        dialog.run()
        dialog.destroy()

    def _on_label_click(self, label, event, option):
        if event.button == 3 and option.changed:  # Right mouse button
            if hasattr(self, 'label_menu_handler'):
                self.label_menu_reset.disconnect(self.label_menu_handler)
            self.label_menu_handler = self.label_menu_reset.connect('activate', self._on_reset_option_clicked, option)
            self.label_menu.popup(None, None, None, None, event.button, event.time)

    def _on_reset_option_clicked(self, widget, option):
        option.reset()
        option.enabled = self.config.has_option(*self.options[option])

    def _on_ok_clicked(self, *args):
        if self.save():
            Gtk.main_quit()

    def _on_cancel_clicked(self, *args):
        Gtk.main_quit()

    def _on_reset_clicked(self, *args):
        for option, (section, key) in self.options.items():
            option.reset()
            option.enabled = self.config.has_option(section, key)

    def _on_indicator_changed(self, selection):
        model, it = selection.get_selected()
        self.indicators_notebook.set_current_page(model[it][IndicatorOption.Model.PAGE])

def main(argv=None, localedir=None, localedomain='lightdm-another-gtk-greeter-settings'):
    parser = argparse.ArgumentParser()
    parser.add_argument("--greeter-config", dest='greeter-config', default='/etc/lightdm/lightdm-another-gtk-greeter.conf', help="Greeter configuartion file")
    parser.add_argument("--greeter-config-output", dest='greeter-config-output')
    parser.add_argument("--lightdm-config", dest='lightdm-config', default='/etc/lightdm/lightdm.conf', help="Lightdm configuartion file")
    parser.add_argument("--greeter-data", dest='greeter-data', default='/usr/share/lightdm-another-gtk-greeter', help="Lightdm data directory")
    parser.add_argument("--ui-file", dest='ui-file', default='interface.ui')
    v = vars(parser.parse_args(args=argv))
    global Gtk
    from gi.repository import Gtk  # @UnusedImport
    if localedir:
        locale.bindtextdomain(localedomain, localedir)
        gettext.bindtextdomain(localedomain, localedir)
        gettext.textdomain(localedomain)
        v['localedomain'] = localedomain
    Application(v).run()

if __name__ == '__main__':
    import sys
    main(argv=sys.argv[1:])
