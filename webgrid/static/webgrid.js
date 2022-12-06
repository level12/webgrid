
var datagrid_active_filters = [];
var _datagrid_is_loaded = false;

/*
   ensure we have a definition for the `_` function.
   when i18n is enabled, this function should already exist.
 */
if (typeof _ === "undefined") {
    var _ = function (msg) { return msg; };
}

$(document).ready(function() {
    // sorting
    datagrid_toggle_sort_selects();
    $('.datagrid .header .sorting select').change(datagrid_toggle_sort_selects);

    // filtering
    datagrid_prep_filters();
    $('.datagrid .filters .operator select').change(datagrid_on_operator_change);
    $('.datagrid .filters .add-filter select').change(datagrid_add_filter);

    $('.inputs1 select').change(function() {
        $(this).siblings('input').val($(this).val());
    });
    $('.datagrid .export-link').click(verify_export);
    $('.datagrid form.header').submit(datagrid_cleanup_before_form_submission);
    _datagrid_is_loaded = true;
});

/*
 datagrid_activate_mselect_ui()

 Called to activate the multi-select ui on a select element.

*/
function datagrid_activate_mselect_ui(jq_select) {
    var all_opt = $(jq_select).find('option[value="-1"]');
    var use_all_opt = (all_opt.text() == _('-- All --', 'webgrid'));
    if ( use_all_opt ) {
        $(all_opt).detach();
    }
    if (jq_select.data('multipleSelect')) {
        jq_select.hide();
    } else {
        jq_select.webgridMultipleSelect({
            minumimCountSelected: 2,
            filter: true
        });
        jq_select.parent().find('.ms-parent > button, .ms-drop').each(function() {
            $(this).css('width', $(this).width() + 60);
        });
    }
    jq_select.siblings('.ms-parent').show();
    jq_select.attr('multiple', 'multiple');
    if ( use_all_opt ) {
        $(all_opt).prependTo(jq_select);
    }
}

/*
 datagrid_add_filter()

 Called when the Add Filter select box is changed. Shows the operator and input
 fields that corresponds to the filter selected.

*/
function datagrid_add_filter() {
    var jq_afs = $('.datagrid .filters .add-filter select');
    var filter_key = jq_afs.val();
    if( filter_key != '') {
        datagrid_activate_filter(filter_key);
        jq_afs.val('');
    }
}


/*
 datagrid_prep_filters()

 Called when the page is loaded, this function loops through the filter controls
 table looking for filters that should be active (because of their initial
 operator and input values) and shows the filter's input fields.

*/
function datagrid_prep_filters(){
    $('.datagrid .filters tr').each(function(){
        var jq_tr = $(this);
        // Added _filter to address CSS collision with Bootstrap
        // Ref: https://github.com/level12/webgrid/issues/28
        var filter_key = jq_tr.attr('class').replace(new RegExp('_filter$'),'');
        if( filter_key != 'add-filter') {
            var op_select = jq_tr.find('.operator select');
            if( op_select.val() != '' ) {
                // filter should be active, so activate it
                datagrid_activate_filter(filter_key);
            } else {
                // the filter is not active, hide the row
                jq_tr.hide();
            }
            datagrid_toggle_filter_inputs(jq_tr);
        }
    });
}

/*
 datagrid_activate_filter()

 Called initially when the page is loaded and also when the "Add Filter" select
 box is changed to show the row and controls for the given filter key.

*/
function datagrid_activate_filter(filter_key) {
    // Added _filter to address CSS collision with Bootstrap
    // Ref: https://github.com/level12/webgrid/issues/28
    var jq_tr = $('.datagrid .filters tr.' + filter_key+ "_filter");

    if (_datagrid_is_loaded) {
        // move user-selected filter to the end of the list, so it shows up right where it was selected
        // note, we don't preserve this ordering through page refresh
        var detached_row = jq_tr.detach();
        detached_row.appendTo('.datagrid .filters tbody');
    }

    // show the filter's row of controls
    jq_tr.show();

    if (_datagrid_is_loaded) {
        var primary_filter_op = jq_tr.find('td.operator option[data-render="primary"]').attr('value');
        jq_tr.find('td.operator select').val(primary_filter_op);
        // ensure all event handlers (including custom ones) run for op select
        jq_tr.find('td.operator select').change();
    }

    // make sure the option in the "Add Filter" select box for this
    // filter is disabled
    var jq_option = $('.datagrid .filters .add-filter option[value="'+filter_key+'"]');
    jq_option.attr('disabled', 'disabled');
}

/*
 datagrid_on_operator_change()

 Called when an operator select box is changed, it calls
 datagrid_toggle_filter_inputs() for the filter in question so that the input
 fields for the filter can be displayed properly.

*/
function datagrid_on_operator_change() {
    var jq_op_select = $(this);
    var jq_tr = jq_op_select.closest('tr');
    datagrid_toggle_filter_inputs(jq_tr);
}

/*
 datagrid_toggle_filter_inputs()

 Handles showing or hiding the input fields (input/select/multi-select UI) for a
 given filter row.

*/
function datagrid_toggle_filter_inputs(jq_filter_tr) {
    // Added _filter to address CSS collision with Bootstrap
    // Ref: https://github.com/level12/webgrid/issues/28
    var filter_key = jq_filter_tr.attr('class').replace(new RegExp('_filter$'), '');
    var op_key = jq_filter_tr.find('.operator select').val();
    var fields1 =  jq_filter_tr.find('.inputs1').children();
    var fields2 = jq_filter_tr.find('.inputs2').children();
    var v1name = 'v1('+filter_key+')';

    jq_filter_tr.find('[form="webgrid-fake"]').remove();

    if( op_key == null ) {
        fields1.show();
    } else if( op_key == '' ) {
        fields1.hide();
        fields1.val('');

        fields2.hide();
        fields2.val('');
    } else {
        var op_data = datagrid_data[filter_key][op_key];
        var field_type = op_data.field_type;
        var html_input_type = op_data.html_input_type;
        if( field_type == null ) {
            fields1.hide();
            fields1.val('');
        } else {
            fields1.show();
            fields1.siblings('.ms-parent').hide();
            jq_filter_tr.find('.inputs1 select[multiple]').each(function(){
                datagrid_activate_mselect_ui($(this));
            });
            if ( field_type.substring(0,6) == 'select' ) {
                jq_filter_tr.find('.inputs1 input').hide();
                if ( field_type == 'select+input' ) {
                    jq_filter_tr.find('.inputs1 input[name="' + v1name + '"]').removeAttr('name');
                    jq_filter_tr.find('.inputs1 select').attr('name', v1name);
                }
                if (_datagrid_is_loaded) {
                    var mselect = jq_filter_tr.find('.inputs1 select').data('multipleSelect');
                    if (mselect) {
                        // note, directly opening did not seem to work, need to call in separate function
                        setTimeout(function(){mselect.open();}, 10);
                    }
                }
            } else {
                if (html_input_type) {
                    jq_filter_tr.find('.inputs1 input').attr('type', html_input_type);
                    jq_filter_tr.find('.inputs2 input').attr('type', html_input_type);
                }
                if (_datagrid_is_loaded) {
                    jq_filter_tr.find('.inputs1 input').val('');
                }
                jq_filter_tr.find('.inputs1 input').show();
                jq_filter_tr.find('.inputs1 select').hide();
                jq_filter_tr.find('.inputs1 .ms-parent').hide();
                jq_filter_tr.find('.inputs1 input').attr('name',v1name);
                jq_filter_tr.find('.inputs1 select').removeAttr('name');
                if (_datagrid_is_loaded) {
                    jq_filter_tr.find('.inputs1 input').focus();
                }
            }
        }
        if( field_type == '2inputs' || field_type == 'select+input' ) {
            fields2.show();
        } else {
            fields2.hide();
            fields2.val('');
        }

        wgDatetimePolyfill.replaceInputs.bind(wgDatetimePolyfill)();
    }
}

/*
 datagrid_toggle_sort_selects()

 Called when any of the sorting related select boxes change, it handles hiding
 and showing the select boxes.

*/
function datagrid_toggle_sort_selects() {
    var jq_dds = $('.datagrid .header .sorting dd');
    if (jq_dds.length == 0) return;
    var dd1 = jq_dds.eq(0)
    var dd2 = jq_dds.eq(1)
    var dd3 = jq_dds.eq(2)
    var sb1 = dd1.find('select');
    var sb2 = dd2.find('select');
    var sb3 = dd3.find('select');

    if( sb1.val() == '' ) {
        dd2.hide();
        sb2.val('');
        dd3.hide();
        sb3.val('');
    } else {
        dd2.show();
        if( sb2.val() == '' ) {
            dd3.hide();
            sb3.val('');
        } else {
            dd3.show();
        }
    }

    $('dl.sorting select option').removeAttr('disabled');
    disable_sort(sb3);
    disable_sort(sb2);
    disable_sort(sb1);
}

/*
 disable_sort()

 Takes the target_id select box and grays out options that have been chosen in sb1 and sb2.

*/
function disable_sort(sb) {
    if ($(sb).val() == '') return;
    var sbval = $(sb).val().replace(/^-/, "");
    $('dl.sorting select[id!="'+$(sb).attr('id')+'"]').find(
        'option[value="'+sbval+'"], option[value="-'+sbval+'"]'
    ).attr('disabled', 'disabled');
}

function verify_export(event) {
    if (!datagrid_confirm_export.confirm_export) {
        return true;
    }
    var result = confirm(
        'You are about to export ' + datagrid_confirm_export.record_count + ' records. ' +
        'This operation may take a while, do you want to continue?'
    );
    if (!result) {
        event.preventDefault();
        return false;
    }
    return true;
}

/*
 datagrid_cleanup_before_form_submission()

 Called before form submission to remove filter form rows that are unused. This reduces the
 size of the URL by not including query parameters for filters that are empty.
 */
function datagrid_cleanup_before_form_submission() {
    $('.datagrid .filters tr').each(function(idx, row) {
        var $row = $(row);
        var $operator = $row.find('.operator select');
        if ($operator.length && $operator.val() === '') {
            $row.remove();
        }
    });
    return true;
}


/* Many browsers support datetime-local input type, but Firefox currently does not. The
following polyfill has some minimal edits to go with Webgrid usage, and provides Firefox
with a similar UX to other browsers. The datetime-local is shown as two inputs of
supported types, and input is combined into a hidden field for submission as a single
value. */

/**
 * datetime-polyfill
 * @version 1.0.0
 * @author Andchir<andchir@gmail.com>
 */

 (function (factory) {

    if ( typeof define === 'function' && define.amd ) {

        // AMD. Register as an anonymous module.
        define([], factory);

    } else if ( typeof exports === 'object' ) {

        // Node/CommonJS
        module.exports = factory();

    } else {

        // Browser globals
        window.WGDatetimePolyfill = factory();
    }

}(function( ) {

    'use strict';

    function WGDatetimePolyfill(initOptions) {
        const defaultOptions = {force: false};
        const options = {
            ...defaultOptions,
            ...(initOptions || {}),
        };

        const self = this;

        this.init = function(force) {
            if (force) {
                this.replaceInputs.bind(this)();
            } else {
                this.onReady(this.replaceInputs.bind(this));
            }
        };

        this.onReady = function(cb) {
            if (document.readyState !== 'loading') {
                cb();
            } else {
                document.addEventListener('DOMContentLoaded', cb);
            }
        };

        this.replaceInputs = function() {
            const replacedInputs = [];
            const inputs = document.querySelectorAll(
                '.datagrid input[type="datetime"], .datagrid input[type="datetime-local"]'
            );

            const onChangeFunc = function(input, inpDate, inpTime) {
                const valueDate = inpDate.value;
                const valueTime = inpTime.value;
                if (!valueDate || !valueTime) {
                    input.value = '';
                    return;
                }
                input.value = valueDate + 'T' + valueTime;
            };

            Array.from(inputs)
                .filter(function (item,index) { return item.style.display!="none" } )
                .forEach(function(input) {
                if (['datetime', 'datetime-local'].indexOf(input.type) > -1) {
                    return;
                }
                input.type = 'hidden';
                const values = self.parseValue(input.value);
                const inpDate = self.createInput('date', input.className, {
                    width: '55%',
                    boxSizing: 'border-box',
                    display: 'block',
                    float: 'left',
                    borderWidth: '1px',
                    borderRight: 0,
                    borderTopRightRadius: 0,
                    borderBottomRightRadius: 0,
                    marginTop: '3px'
                }, function() {
                    onChangeFunc(input, inpDate, inpTime);
                });
                inpDate.setAttribute('name', 'polyfill_' + input.name);
                inpDate.setAttribute('form', 'webgrid-fake');
                if (values.length === 2) {
                    inpDate.value = values[0];
                }

                const inpTime = self.createInput('time', input.className, {
                    width: '45%',
                    boxSizing: 'border-box',
                    display: 'block',
                    float: 'left',
                    borderWidth: '1px',
                    borderLeft: 0,
                    borderTopLeftRadius: 0,
                    borderBottomLeftRadius: 0,
                    marginTop: '3px'
                }, function() {
                    onChangeFunc(input, inpDate, inpTime);
                });
                inpTime.setAttribute('name', 'polyfill_' + input.name);
                inpTime.setAttribute('form', 'webgrid-fake');
                if (values.length === 2) {
                    inpTime.value = values[1];
                }

                const divEl = document.createElement('div');
                divEl.style.clear = 'left';

                if(input.nextSibling){
                    input.parentNode.insertBefore(inpDate, input.nextSibling);
                    input.parentNode.insertBefore(inpTime, input.nextSibling);
                    input.parentNode.insertBefore(divEl, input.nextSibling);
                }else{
                    input.parentNode.appendChild(inpDate);
                    input.parentNode.appendChild(inpTime);
                    input.parentNode.appendChild(divEl);
                }

                replacedInputs.push(input);
            });

            return replacedInputs;
        };

        this.createInput = function(type, className, styles, onChange) {
            const inp = document.createElement('input');
            inp.type = type;
            inp.className = className;
            if (styles) {
                this.css(inp, styles);
            }
            if (typeof onChange === 'function') {
                inp.onchange = onChange.bind(inp);
            }
            return inp;
        };

        this.parseValue = function(value) {
            return value && /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)
                ? value.split('T')
                : [];
        };

        this.css = function (el, styles) {
            this.forEachObj(styles, function (key, val) {
                el.style[key] = val;
            });
        };

        this.forEachObj = function (obj, callback) {
            for (let prop in obj) {
                if (obj.hasOwnProperty(prop)) {
                    callback(prop, obj[prop]);
                }
            }
            return obj;
        };

        this.init(options.force);
    }

    return WGDatetimePolyfill;
}));

const wgDatetimePolyfill = new WGDatetimePolyfill();