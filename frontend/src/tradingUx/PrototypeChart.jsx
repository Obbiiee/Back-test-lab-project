import {useEffect,useRef,useState} from 'react';
import {createChart,CandlestickSeries} from 'lightweight-charts';
import ChartObjectOverlay from '../chart/ChartObjectOverlay.jsx';
import RiskRewardGeometry from '../trading/RiskRewardGeometry.jsx';
import {RiskRewardController} from '../trading/RiskRewardController.js';
import {roundPrice,DEMO_CANDLES} from './prototypeModel.js';
import {timeAtLogical} from '../chart/coordinates.js';
const controller=new RiskRewardController();
const geometry=props=><RiskRewardGeometry {...props} selected={false}/>;
const priceAnchor=(_,index)=>index===1||index===2;
const handles=points=>points.map((p,index)=>index===1||index===2?{...p,x:points[3].x}:p);
export default function PrototypeChart({plan,placing,locked,hidden,onPlace,onEdit}){
  const container=useRef(null),[api,setApi]=useState(null);
  useEffect(()=>{
    const node=container.current,chart=createChart(node,{layout:{background:{color:'#08090b'},textColor:'#bac5d5'},grid:{vertLines:{color:'#151b24'},horzLines:{color:'#151b24'}},height:node.clientHeight,width:node.clientWidth});
    const series=chart.addSeries(CandlestickSeries,{priceFormat:{type:'price',precision:3,minMove:.001}});series.setData(DEMO_CANDLES);chart.timeScale().fitContent();
    setApi({chart,series});
    const resize=new ResizeObserver(()=>chart.resize(node.clientWidth,node.clientHeight));resize.observe(node);
    return ()=>{resize.disconnect();chart.remove();};
  },[]);
  const drawing={id:'prototype-plan',type:plan.side==='Buy'?'long-position':'short-position',points:[{time:plan.time,price:plan.entry},{time:plan.time,price:plan.sl},{time:plan.time,price:plan.tp},{time:plan.time+900*16,price:plan.entry}],locked,hidden,alwaysShowStats:false};
  const editPoint=(_,index,point)=>{
    if(locked)return;
    const object=controller.resize(drawing,index,{...point,price:roundPrice(point.price)},DEMO_CANDLES);
    onEdit({time:object.points[0].time,entry:roundPrice(object.points[0].price),sl:roundPrice(object.points[1].price),tp:roundPrice(object.points[2].price)},index);
  };
  const place=event=>{
    if(!placing||!api)return;
    const box=container.current.getBoundingClientRect(),x=event.clientX-box.left,y=event.clientY-box.top;
    if(y<0||y>api.chart.paneSize(0).height)return;
    const price=api.series.coordinateToPrice(y),time=timeAtLogical(DEMO_CANDLES,api.chart.timeScale().coordinateToLogical(x));
    if(price!=null&&time!=null){event.stopPropagation();onPlace(roundPrice(price),time);}
  };
  return <div className="ux-chart" aria-label="Synthetic planning chart" onClickCapture={place}><div ref={container} className="ux-chart-canvas"/>{api&&<ChartObjectOverlay chart={api.chart} series={api.series} candles={DEMO_CANDLES} drawings={placing||plan.workflow!=='PLANNED'||![plan.entry,plan.sl,plan.tp].every(Number.isFinite)?[]:[drawing]} renderGeometry={geometry} isPriceOnlyAnchor={priceAnchor} handleProjection={handles} layerName="Prototype planning levels" selectedId="prototype-plan" drawingMode={placing?'long-position':'none'} onSelect={()=>{}} onStartDrag={()=>api.chart.applyOptions({handleScroll:false,handleScale:false})} onEndDrag={()=>api.chart.applyOptions({handleScroll:true,handleScale:true})} onUpdatePoint={editPoint} onMoveDrawing={(_,points)=>{if(!locked)onEdit({time:points[0].time,entry:roundPrice(points[0].price),sl:roundPrice(points[1].price),tp:roundPrice(points[2].price)},0);}} onContextMenu={()=>{}} onPlacePoint={event=>{const price=api.series.coordinateToPrice(event.point.y);if(price!=null)onPlace(roundPrice(price),event.time);}}/>}<span className="ux-chart-label">DEMO SYNTHETIC · 15m · no future market data</span></div>;
}
