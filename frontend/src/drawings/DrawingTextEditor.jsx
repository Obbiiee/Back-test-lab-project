import { useState } from 'react';
// A transient editor only; canvas and canonical model own the annotation itself.
export default function DrawingTextEditor({ editor, onSave, onCancel }) {
  const [text, setText] = useState(editor.text);
  return <form className="primitive-text-editor" aria-label="Drawing text editor"
    style={{ position:'absolute',right:18,top:150,zIndex:70,width:260,padding:12,background:'#20232a',border:'1px solid #464b55',borderRadius:6,color:'#ddd' }}
    onSubmit={event=>{event.preventDefault();onSave(text);}}
    onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onCancel();}}}>
    <label>Text<textarea aria-label="Drawing text content" autoFocus maxLength={2000} rows={4} value={text}
      style={{display:'block',width:'100%',boxSizing:'border-box',margin:'8px 0',background:'#10141b',color:'#ddd',border:'1px solid #464b55'}}
      onChange={event=>setText(event.target.value)} /></label>
    <button type="submit" disabled={!text.trim()}>Save text</button>{' '}
    <button type="button" onClick={onCancel}>Cancel text</button>
  </form>;
}
