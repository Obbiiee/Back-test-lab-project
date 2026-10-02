import { useEffect, useRef } from 'react';
import { DrawingManager } from 'lightweight-charts-drawing';
import { fromNative, nativeKind, toNative } from '../drawings/native';

export default function NativeDrawings(props) {
  const latest = useRef(props), manager = useRef(null), muted = useRef(false), snapshot = useRef(null), signature = useRef('');
  useEffect(()=>{ latest.current = props; });
  const {chart,series} = props;
  useEffect(()=>{
    if (!chart || !series) return;
    const drawings = new DrawingManager(chart, series, { bars:()=>latest.current.candles, magnet:'off', timeInfo:()=>({timeZone:'UTC',intraday:true}) });
    manager.current = drawings;
    const off = [
      drawings.on('change', list=>{
        if(muted.current) return;
        snapshot.current ??= latest.current.drawings;
        const originals = latest.current.drawings;
        const next = [...originals.filter(item=>!nativeKind(item.type)), ...list.map(item=>fromNative(item,originals.find(old=>old.id===item.id)))];
        signature.current = JSON.stringify(next.map(toNative).filter(Boolean));
        latest.current.onChange(next);
      }),
      drawings.on('gestureEnd',()=>{if(snapshot.current){latest.current.onGesture(snapshot.current);snapshot.current=null;}}),
      drawings.on('selection',ids=>{ if(!muted.current) latest.current.onSelect(ids[0]||null); }),
      drawings.on('tool',kind=>{ if(!muted.current && kind==null && nativeKind(latest.current.drawingMode)) latest.current.onDrawingModeChange('none'); }),
      drawings.on('textEdit',item=>latest.current.onEdit(fromNative(item,latest.current.drawings.find(old=>old.id===item.id)))),
      drawings.on('tableEdit',(item,cell)=>latest.current.onTableEdit(item,cell,drawings)),
    ];
    return ()=>{ off.forEach(fn=>fn()); drawings.destroy(); manager.current=null; signature.current=''; };
  },[chart,series]);
  useEffect(()=>{
    const instance=manager.current;if(!instance)return;
    const json=JSON.stringify(props.drawings.map(toNative).filter(Boolean));
    if(json!==signature.current){muted.current=true;instance.importJSON(json);signature.current=json;muted.current=false;}
    muted.current=true;instance.select(props.selectedId?[props.selectedId]:[]);muted.current=false;
  },[props.drawings,props.selectedId,chart,series]);
  useEffect(()=>{
    const instance=manager.current;if(!instance)return;
    muted.current=true;
    instance.setTool(nativeKind(props.drawingMode),props.drawingMode.startsWith('emoji-')?{glyph:{'emoji-smile':'🙂','emoji-star':'⭐','emoji-check':'✅','emoji-warning':'⚠️'}[props.drawingMode]}:undefined);
    instance.setMagnet(props.magnet?'weak':'off');instance.setStayInDrawingMode(props.keepDrawing);
    instance.setInterval(props.interval);muted.current=false;
  },[props.drawingMode,props.magnet,props.keepDrawing,props.interval,chart,series]);
  useEffect(()=>{manager.current?.redraw();},[props.candles]);
  return null;
}
