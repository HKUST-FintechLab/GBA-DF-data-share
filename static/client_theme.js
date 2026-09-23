(() => {
  const canvas = document.querySelector("#themeStage");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const state = {width:0,height:0,dpr:1,step:1,time:0,last:0,frame:0,particles:[],slots:[]};

  function resize(){
    state.dpr=Math.min(devicePixelRatio||1,2);
    state.width=canvas.clientWidth||innerWidth;
    state.height=canvas.clientHeight||innerHeight;
    canvas.width=Math.max(1,Math.round(state.width*state.dpr));
    canvas.height=Math.max(1,Math.round(state.height*state.dpr));
    context.setTransform(state.dpr,0,0,state.dpr,0,0);
    layoutHitZones();
  }
  function line(x1,y1,x2,y2,color,width=1,dash=[]){
    context.save();context.strokeStyle=color;context.lineWidth=width;context.setLineDash(dash);
    context.beginPath();context.moveTo(x1,y1);context.lineTo(x2,y2);context.stroke();context.restore();
  }
  function dot(x,y,r,color,glow=0){
    context.save();
    if(glow){context.shadowColor=color;context.shadowBlur=glow;}
    context.fillStyle=color;context.beginPath();context.arc(x,y,r,0,Math.PI*2);context.fill();
    context.restore();
  }
  function label(text,x,y,align="center",color="#66809f"){
    context.save();context.textAlign=align;context.fillStyle=color;
    context.font="9px 'SF Mono',Consolas,monospace";
    context.fillText(String(text).toUpperCase().split("").join(" "),x,y);context.restore();
  }
  function backdrop(){
    const {width,height}=state;
    const gradient=context.createRadialGradient(width*.5,height*.35,0,width*.5,height*.35,
      Math.max(width,height)*.75);
    gradient.addColorStop(0,"#1b3155");gradient.addColorStop(1,"#0d1a2e");
    context.fillStyle=gradient;context.fillRect(0,0,width,height);
  }
  const modalitySketch={
    eyegaze(ctx,width,height,time,selected){
      const cx=width/2,cy=height*.5,faceWidth=width*.20,faceHeight=height*.30;
      const ink=selected?"rgba(78,168,255,":"rgba(122,168,235,";
      ctx.strokeStyle=ink+(selected?".3":".18")+")";ctx.lineWidth=1;
      ctx.beginPath();ctx.ellipse(cx,cy,faceWidth,faceHeight,0,0,Math.PI*2);ctx.stroke();
      const leftEye=[cx-faceWidth*.42,cy-faceHeight*.22];
      const rightEye=[cx+faceWidth*.42,cy-faceHeight*.22];
      const mouth=[cx,cy+faceHeight*.44];
      [leftEye,rightEye].forEach(([x,y])=>{
        ctx.beginPath();ctx.ellipse(x,y,faceWidth*.26,faceHeight*.12,0,0,Math.PI*2);ctx.stroke();
        ctx.beginPath();ctx.arc(x,y,faceHeight*.055,0,Math.PI*2);
        ctx.fillStyle=ink+(selected?".55":".3")+")";ctx.fill();
      });
      ctx.beginPath();ctx.moveTo(mouth[0]-faceWidth*.3,mouth[1]);
      ctx.quadraticCurveTo(mouth[0],mouth[1]+faceHeight*.12,mouth[0]+faceWidth*.3,mouth[1]);ctx.stroke();
      const targets=[[mouth,7],[mouth,6],[leftEye,3],[mouth,8],[rightEye,3],[mouth,6],[leftEye,2.5]];
      const points=targets.map(([[x,y],dwell],index)=>[
        x+Math.sin(time*.7+index*2.1)*faceWidth*.16,
        y+Math.cos(time*.6+index*1.7)*faceHeight*.13,dwell
      ]);
      ctx.strokeStyle=ink+(selected?".45":".25")+")";ctx.lineWidth=1;ctx.beginPath();
      points.forEach((point,index)=>index?ctx.lineTo(point[0],point[1]):ctx.moveTo(point[0],point[1]));ctx.stroke();
      const live=Math.floor(time*1.4)%points.length;
      points.forEach((point,index)=>{
        const hot=index===live;
        ctx.beginPath();ctx.arc(point[0],point[1],point[2]*(hot?1.35:1),0,Math.PI*2);
        ctx.fillStyle=ink+(selected?(hot?".4":".16"):".1")+")";ctx.fill();
        ctx.strokeStyle=ink+(selected?(hot?".95":".5"):".32")+")";ctx.lineWidth=hot?1.4:1;ctx.stroke();
      });
    },
    action(ctx,width,height,time,selected){
      const cx=width/2,top=height*.14,scale=height*.155;
      const sway=Math.sin(time*1.9),counter=Math.cos(time*1.9),points={};
      const set=(index,x,y)=>{points[index]=[x,y];};
      set(0,cx,top+scale*.34);set(2,cx-scale*.13,top+scale*.24);set(5,cx+scale*.13,top+scale*.24);
      set(7,cx-scale*.26,top+scale*.30);set(8,cx+scale*.26,top+scale*.30);
      set(11,cx-scale*.52,top+scale*.95);set(12,cx+scale*.52,top+scale*.95);
      set(13,cx-scale*.80+sway*scale*.14,top+scale*1.55);
      set(14,cx+scale*.80-sway*scale*.14,top+scale*1.55);
      set(15,cx-scale*.92+sway*scale*.30,top+scale*2.15);
      set(16,cx+scale*.92-sway*scale*.30,top+scale*2.15);
      set(23,cx-scale*.34,top+scale*2.05);set(24,cx+scale*.34,top+scale*2.05);
      set(25,cx-scale*.40+counter*scale*.16,top+scale*2.90);
      set(26,cx+scale*.40-counter*scale*.16,top+scale*2.90);
      set(27,cx-scale*.44+counter*scale*.30,top+scale*3.70);
      set(28,cx+scale*.44-counter*scale*.30,top+scale*3.70);
      const bones=[[11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],
        [23,25],[25,27],[24,26],[26,28],[0,2],[2,7],[0,5],[5,8]];
      ctx.globalAlpha=selected?1:.5;ctx.lineCap="round";ctx.strokeStyle=selected?"#4ea8ff":"#7aa8eb";ctx.lineWidth=1.5;
      bones.forEach(([a,b])=>{ctx.beginPath();ctx.moveTo(...points[a]);ctx.lineTo(...points[b]);ctx.stroke();});
      Object.entries(points).forEach(([index,[x,y]])=>{
        const face=Number(index)<=10;ctx.beginPath();ctx.arc(x,y,face?2.6:2.9,0,Math.PI*2);
        if(face){
          ctx.strokeStyle="#ffa95c";ctx.lineWidth=1.2;ctx.stroke();
          ctx.strokeStyle=selected?"#4ea8ff":"#7aa8eb";ctx.lineWidth=1.5;
        }else{ctx.fillStyle=selected?"#eaf2ff":"#a3b9d8";ctx.fill();}
      });
      ctx.globalAlpha=1;
    },
    neuro(ctx,width,height,time,selected){
      const color=selected?"rgba(78,168,255,":"rgba(122,168,235,";
      for(let channel=0;channel<4;channel++){
        const y=height*(.28+channel*.15);
        ctx.strokeStyle=color+(selected?.75-channel*.13:.4-channel*.07)+")";ctx.lineWidth=1.1;ctx.beginPath();
        for(let x=width*.14;x<=width*.86;x+=2){
          const phase=(x/width)*9+time*(1.6+channel*.35)+channel*2;
          ctx.lineTo(x,y+Math.sin(phase)*height*.045+Math.sin(phase*2.7+channel)*height*.028);
        }
        ctx.stroke();
      }
    }
  };
  modalitySketch.action_cdp=(ctx,width,height,time,selected)=>{
    /* CDP keeps the pose input, but its fixed adapter has two feature branches before fusion.
       Draw a recognisable bottom-up binary tree behind the skeleton: one trunk, two branch levels,
       and four leaves. This reads as TreeFusion rather than as extra limbs. */
    const centerX=width/2;
    const nodes={
      root:[centerX,height*.86], trunk:[centerX,height*.63],
      left:[centerX-width*.16,height*.43], right:[centerX+width*.16,height*.43],
      ll:[centerX-width*.29,height*.22], lr:[centerX-width*.08,height*.22],
      rl:[centerX+width*.08,height*.22], rr:[centerX+width*.29,height*.22]
    };
    const edges=[["root","trunk"],["trunk","left"],["trunk","right"],
      ["left","ll"],["left","lr"],["right","rl"],["right","rr"]];
    ctx.save();
    ctx.globalAlpha=selected?.8:.42;ctx.lineWidth=1.15;ctx.lineCap="round";
    edges.forEach(([from,to],index)=>{
      const warm=index>=5;ctx.strokeStyle=warm?"#9a6636":"#3c6fa8";
      ctx.beginPath();ctx.moveTo(...nodes[from]);ctx.lineTo(...nodes[to]);ctx.stroke();
    });
    Object.entries(nodes).forEach(([name,[x,y]])=>{
      const leaf=["ll","lr","rl","rr"].includes(name);
      ctx.fillStyle="#0d1a2e";ctx.beginPath();ctx.arc(x,y,leaf?3.6:3,0,Math.PI*2);ctx.fill();
      ctx.strokeStyle=(name==="rl"||name==="rr")?"#9a6636":"#4ea8ff";
      ctx.beginPath();ctx.arc(x,y,leaf?3.6:3,0,Math.PI*2);ctx.stroke();
    });
    ctx.restore();
    modalitySketch.action(ctx,width,height,time+.55,selected);
  };
  function pickSlots(){
    const modalityList=typeof MODS==="undefined"?[]:MODS;
    const count=Math.max(1,modalityList.length);
    const boxWidth=Math.min(300,(state.width*.78)/count),gap=Math.min(70,state.width*.05);
    const total=boxWidth*count+gap*(count-1),start=(state.width-total)/2,centerY=state.height*.36;
    return modalityList.map((item,index)=>({
      key:item.key,x:start+index*(boxWidth+gap),y:centerY-110,w:boxWidth,h:220,
      cx:start+index*(boxWidth+gap)+boxWidth/2,cy:centerY
    }));
  }
  function layoutHitZones(){
    const elements=document.querySelectorAll("#mods .mod");
    if(document.documentElement.dataset.theme!=="console"){
      state.slots=[];
      elements.forEach(element=>{
        element.style.removeProperty("left");element.style.removeProperty("top");
        element.style.removeProperty("width");element.style.removeProperty("height");
      });
      return;
    }
    state.slots=pickSlots();
    elements.forEach((element,index)=>{
      const slot=state.slots[index];if(!slot)return;
      element.style.left=`${slot.x}px`;element.style.top=`${slot.y}px`;
      element.style.width=`${slot.w}px`;element.style.height=`${slot.h}px`;
    });
  }
  function fitTitleFont(text,maxWidth,preferred){
    let size=preferred;
    while(size>15){
      context.font=`300 ${size}px Georgia,serif`;
      if(context.measureText(text).width<=maxWidth)break;
      size--;
    }
    return size;
  }
  function titleLines(item,name,maxWidth){
    if(item.key!=="action_cdp")return [name];
    const bracket=name.search(/[（(]/);
    if(bracket>0)return [name.slice(0,bracket).trim(),name.slice(bracket).trim()];
    if(name.includes("CDP")){
      const marker=name.indexOf("CDP");
      return [name.slice(0,marker).trim(),name.slice(marker).trim()];
    }
    return [name];
  }
  function wrapCanvasText(text,maxWidth,maxLines=2){
    if(!text)return [""];
    const spaced=text.includes(" "),tokens=spaced?text.split(/\s+/):Array.from(text);
    const separator=spaced?" ":"",lines=[];let current="";
    for(const token of tokens){
      const candidate=current?`${current}${separator}${token}`:token;
      if(current&&context.measureText(candidate).width>maxWidth&&lines.length<maxLines-1){
        lines.push(current);current=token;
      }else current=candidate;
    }
    if(current)lines.push(current);
    return lines;
  }
  function sceneOne(){
    const modalityList=typeof MODS==="undefined"?[]:MODS;
    const selection=typeof sel==="undefined"?null:sel;
    if(state.slots.length!==modalityList.length)layoutHitZones();
    state.slots.forEach((slot,index)=>{
      const item=modalityList[index];if(!item)return;
      const selected=selection?.modality===item.key,dimmed=selection?.modality&&!selected;
      context.save();
      context.globalAlpha=dimmed?.3:1;context.translate(slot.cx-slot.w/2,slot.cy-92);
      (modalitySketch[item.key]||(()=>{}))(context,slot.w,150,state.time,selected);
      context.restore();
      const traditional=(typeof HANT_MODALITIES==="undefined"?null:HANT_MODALITIES[item.key]);
      const name=(typeof isTraditional!=="undefined"&&isTraditional())?traditional?.name:
        ((typeof isChinese!=="undefined"&&isChinese())?item.zh:item.en);
      const task=(typeof isTraditional!=="undefined"&&isTraditional())?traditional?.task:
        ((typeof isChinese!=="undefined"&&isChinese())?item.task_zh:item.task_en);
      context.textAlign="center";context.globalAlpha=dimmed?.4:1;
      const displayName=name||item.en,titleMaxWidth=slot.w+Math.min(28,state.width*.015);
      const lines=titleLines(item,displayName,titleMaxWidth);
      const preferred=Math.round(Math.min(26,slot.w*.115));
      const fontSize=Math.min(...lines.map(text=>fitTitleFont(text,titleMaxWidth,preferred)));
      const lineHeight=Math.max(20,fontSize*1.08),titleCenterY=slot.cy+(lines.length>1?64:72);
      context.font=`300 ${fontSize}px Georgia,serif`;context.fillStyle=selected?"#eaf1fc":"#a3b9d8";
      lines.forEach((text,lineIndex)=>{
        const y=titleCenterY+(lineIndex-(lines.length-1)/2)*lineHeight;
        context.fillText(text,slot.cx,y);
      });
      const titleBottom=titleCenterY+(lines.length-1)*lineHeight/2;
      context.font="10px 'SF Mono',Consolas,monospace";context.fillStyle="#66809f";
      const taskLines=wrapCanvasText(task||"",slot.w+22,item.key==="action_cdp"?2:1);
      let taskFont=10;
      while(taskFont>8){
        context.font=`${taskFont}px 'SF Mono',Consolas,monospace`;
        if(taskLines.every(text=>context.measureText(text).width<=slot.w+22))break;
        taskFont-=.5;
      }
      const taskY=Math.max(slot.cy+94,titleBottom+23);
      taskLines.forEach((text,lineIndex)=>context.fillText(text,slot.cx,taskY+lineIndex*15));
      context.font="9px 'SF Mono',Consolas,monospace";context.fillStyle=selected?"#4ea8ff":"#3c6fa8";
      const featureLabel=(typeof t==="undefined"?"features":t("feats"));
      const taskBottom=taskY+(taskLines.length-1)*15;
      context.fillText(`${item.n_features} ${featureLabel}`.toUpperCase().split("").join(" "),slot.cx,taskBottom+22);
      if(selected){
        context.strokeStyle="#4ea8ff";context.lineWidth=1;
        const tick=12,x=slot.cx-slot.w/2,y=slot.cy-108,w=slot.w,h=246;
        [[x,y,1,1],[x+w,y,-1,1],[x,y+h,1,-1],[x+w,y+h,-1,-1]].forEach(([px,py,sx,sy])=>{
          context.beginPath();context.moveTo(px+sx*tick,py);context.lineTo(px,py);context.lineTo(px,py+sy*tick);context.stroke();
        });
      }
      context.globalAlpha=1;
    });
  }
  function sceneTwo(){
    const {width,height}=state,cx=width*.28,cy=height*.47,radius=Math.min(width,height)*.19;
    const selection=typeof sel==="undefined"?null:sel;
    context.strokeStyle="rgba(122,168,235,.2)";context.lineWidth=1;
    context.beginPath();context.arc(cx,cy,radius,0,Math.PI*2);context.stroke();
    const sampleCount=Math.min(86,Math.max(8,Math.round((selection?.scan?.n_samples||30)/4)));
    for(let index=0;index<sampleCount;index++){
      const angle=index*2.399963+state.time*.055;
      const r=Math.sqrt(index/sampleCount)*radius*.86;
      dot(cx+Math.cos(angle)*r,cy+Math.sin(angle)*r,1.5,"rgba(255,169,92,.75)",4);
    }
    label(selection?.scan?`${selection.scan.n_samples} local recordings`:"local recordings",
      cx,cy+radius+32);
  }
  function sceneThree(){
    const {width,height}=state,y=height*.46,left=width*.22,right=width*.54;
    const connection=typeof conn==="undefined"?null:conn;
    const live=["on","run","done"].includes(connection?.state);
    line(left+58,y,right-58,y,live?"rgba(78,168,255,.52)":"rgba(122,168,235,.18)",1,[4,6]);
    if(live){
      const progress=(state.time*.18)%1;
      dot(left+58+(right-left-116)*progress,y,3,"#4ea8ff",10);
    }
    [[left,"this node","#ffa95c"],[right,"coordinator",live?"#4ea8ff":"#3c6fa8"]]
      .forEach(([x,text,color],nodeIndex)=>{
        context.fillStyle="rgba(13,26,46,.8)";context.strokeStyle=color;context.lineWidth=1.3;
        context.beginPath();context.arc(x,y,58,0,Math.PI*2);context.fill();context.stroke();
        for(let index=0;index<11;index++){
          const angle=index*2.399963+state.time*(nodeIndex?.02:.05);
          const radius=Math.sqrt(index/11)*37;
          dot(x+Math.cos(angle)*radius,y+Math.sin(angle)*radius,1.5,
            nodeIndex?"rgba(78,168,255,.7)":"rgba(255,169,92,.7)",4);
        }
        label(text,x,y+86);
      });
  }
  function emitPipeline(){
    for(let index=0;index<14;index++){
      state.particles.push({progress:-index*.035,offset:(Math.random()-.5)*20,
        speed:.065+Math.random()*.022});
    }
  }
  function sceneFour(delta){
    const {width,height}=state,y=height*.56,left=width*.07,right=width*.69;
    const points=[0,.24,.48,.72,1].map(value=>left+(right-left)*value);
    const boundary=left+(right-left)*.82;
    line(boundary,y-145,boundary,y+115,"rgba(78,168,255,.38)",1,[4,6]);
    label("this machine",boundary-13,y-153,"right","#9a6636");
    label("coordinator",boundary+13,y-153,"left","#3c6fa8");
    line(points[0],y,points[3],y,"rgba(122,168,235,.18)");
    line(points[3],y,points[4],y,"rgba(78,168,255,.36)");
    const names=["recordings","features","leaf counts","masked","sent"];
    const colors=["#ffa95c","#ffa95c","#eaf2ff","#4ea8ff","#4ea8ff"];
    points.forEach((x,index)=>{
      dot(x,y,7,"#091524");context.strokeStyle=colors[index];context.lineWidth=1.2;
      context.beginPath();context.arc(x,y,7,0,Math.PI*2);context.stroke();
      label(names[index],x,y-29,"center",colors[index]);
    });
    const connection=typeof conn==="undefined"?null:conn;
    if(connection?.state==="run"&&state.particles.length<8)emitPipeline();
    state.particles=state.particles.filter(particle=>{
      particle.progress+=particle.speed*delta;
      if(particle.progress>=1)return false;
      if(particle.progress<0)return true;
      const segment=Math.min(3,Math.floor(particle.progress*4));
      const local=particle.progress*4-segment;
      const x=points[segment]+(points[segment+1]-points[segment])*local;
      const color=segment<2?"#ffa95c":segment===2?"#eaf2ff":"#4ea8ff";
      dot(x,y+particle.offset*Math.sin(Math.PI*particle.progress),2,color,8);
      return true;
    });
  }
  function draw(timestamp){
    const currentTheme=document.documentElement.dataset.theme;
    if(currentTheme!=="console"){state.frame=0;return;}
    if(state.width!==canvas.clientWidth||state.height!==canvas.clientHeight)resize();
    const delta=state.last?Math.min(.05,(timestamp-state.last)/1000):.016;
    state.last=timestamp;
    if(!reducedMotion.matches)state.time+=delta;
    context.clearRect(0,0,state.width,state.height);
    backdrop();
    if(state.step===1)sceneOne();
    else if(state.step===2)sceneTwo();
    else if(state.step===3)sceneThree();
    else sceneFour(delta);
    state.frame=requestAnimationFrame(draw);
  }
  function start(){
    resize();
    if(!state.frame){state.last=0;state.frame=requestAnimationFrame(draw);}
  }
  function stop(){
    if(state.frame)cancelAnimationFrame(state.frame);
    state.frame=0;state.last=0;context.clearRect(0,0,state.width,state.height);
    layoutHitZones();
  }
  window.GBADFTheme={
    change(theme){if(theme==="console")start();else stop();},
    step(step){state.step=step;if(step===1)layoutHitZones();if(step===4)emitPipeline();},
    refresh(){layoutHitZones();}
  };
  addEventListener("resize",resize);
  if(document.documentElement.dataset.theme==="console")start();
})();
