import { Component } from 'react';
export default class WorkspaceErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main style={{padding:32}} role="alert"><h1>Workspace could not be displayed</h1><p>Reload to retry. This recovery screen does not clear or reset your browser data.</p><button onClick={()=>window.location.reload()}>Reload workspace</button></main>;
    return this.props.children;
  }
}
