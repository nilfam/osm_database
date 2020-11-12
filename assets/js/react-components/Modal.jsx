import React, {useState} from 'react';

class YesButton extends React.Component {
    render() {
        return <div className="btn-group" role="group">
            <button type="button" id="dialog-modal-yes-button"
                    className="btn btn-primary btn-hover-green"
                    role="button">
                {this.props.caption}
            </button>
        </div>
    }
}

class NoButton extends React.Component {
    render() {
        return <div className="btn-group" role="group">
            <button type="button" id="dialog-modal-no-button"
                    className="btn btn-primary" data-dismiss="modal" role="button">
                {this.props.caption}
            </button>
        </div>
    }
}


class ModalButton extends React.Component {
    constructor(props) {
        super(props);
    }

    render() {
        if (this.props.order === 'yes-no') {
            return <React.Fragment>
                <YesButton caption="Yes"/>
                <NoButton caption="No"/>
            </React.Fragment>
        }
        else {
            return <React.Fragment>
                <NoButton caption="No"/>
                <YesButton caption="Yes"/>
            </React.Fragment>
        }
    }
}


export default class Modal extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            title: null
        };
    }

    setState(state) {
        this.setState(state);
    }

    onClose(e) {
        this.props.onClose && this.props.onClose(e);
    }

    render() {
        console.log(this);
        console.log(this.props);

        return (
            <div className="modal fade in" id="dialog-modal" tabIndex="-1" role="dialog" aria-labelledby="modalLabel"
                 data-backdrop="static" aria-hidden="true" style={{display: "none"}}>
                <div className="modal-dialog">
                    <div className="modal-content">
                        <div className="modal-header">
                            <h3 className="modal-title">{this.state.title}</h3>
                        </div>
                        <div className="modal-body">{this.props.body}</div>
                        <div className="modal-footer">
                            <div className="btn-group btn-group-justified" role="group" aria-label="group button">
                                <ModalButton order={this.props.order}/>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }
};
