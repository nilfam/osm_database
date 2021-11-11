/* global keyboardJS*/
import {defaultGridOptions, FlexibleGrid} from './flexible-grid';
import {deepCopy, debug} from './utils';


const gridOptions = deepCopy(defaultGridOptions);
gridOptions.rowHeight = 50;


class PageGrid extends FlexibleGrid {
    init() {
        super.init({
            'grid-name': 'labelling',
            'grid-type': 'pages-info',
            // 'default-field': 'label_family',
            gridOptions
        });
    }
}

export const grid = new PageGrid();
const gridStatus = $('#grid-status');
const gridStatusNTotal = gridStatus.find('#ntotal');

let ce;


/**
 * Subscribe to events on the slick grid. This must be called everytime the slick is reconstructed, e.g. when changing
 * screen orientation or size
 */
const subscribeSlickEvents = function () {
    debug('subscribeSlickEvents called');

    grid.subscribeDv('onRowCountChanged', function (e, args) {
        let currentRowCount = args.current;
        gridStatusNTotal.html(currentRowCount);
    });
};


/**
 * Set the focus on the grid right after page is loaded.
 * This is mainly so that user can use Page Up and Page Down right away
 */
const focusOnGridOnInit = function () {
    $($('div[hidefocus]')[0]).focus();
};


let extraArgs = {};

let gridArgs = {};


export const preRun = function () {
    return Promise.resolve();
};


export const run = function (commonElements) {
    ce = commonElements;

    grid.init();

    return grid.initMainGridHeader(gridArgs, extraArgs).then(function () {
        subscribeSlickEvents();
        return grid.initMainGridContent(gridArgs, extraArgs).then(function () {
            focusOnGridOnInit();
        });
    });
};

export const postRun = function () {
    return Promise.resolve();
};

export const viewPortChangeHandler = function () {
    grid.mainGrid.resizeCanvas();
};
