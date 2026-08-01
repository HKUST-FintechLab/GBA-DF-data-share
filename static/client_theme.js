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
      /* An eye, a gaze ray, and where the gaze lands. The previous version drew the whole
         scan path, which at card size read as scattered noise rather than as eye tracking;
         one eye plus three dwell spots says what the modality is at a glance. */
      const ink=selected?"rgba(78,168,255,":"rgba(122,168,235,";
      const heat=selected?1:.55;
      const eyeX=width*.24,eyeY=height*.46,eyeW=width*.115,eyeH=eyeW*.62;
      const frameLeft=width*.47,frameRight=width*.88;
      const frameTop=height*.16,frameBottom=height*.78;
      const frameWidth=frameRight-frameLeft,frameHeight=frameBottom-frameTop;

      // three dwell spots; the gaze rests on each in turn
      const spots=[[frameLeft+frameWidth*.34,frameTop+frameHeight*.34,1.0],
                   [frameLeft+frameWidth*.66,frameTop+frameHeight*.62,.78],
                   [frameLeft+frameWidth*.30,frameTop+frameHeight*.74,.6]];
      const live=Math.floor(time*.55)%spots.length;

      ctx.save();
      // stimulus frame
      ctx.strokeStyle=ink+(selected?".24":".14")+")";ctx.lineWidth=1;
      ctx.strokeRect(frameLeft,frameTop,frameWidth,frameHeight);
      ctx.strokeStyle=ink+(selected?".6":".3")+")";ctx.lineWidth=1.2;
      const corner=8;
      [[frameLeft,frameTop,1,1],[frameRight,frameTop,-1,1],
        [frameLeft,frameBottom,1,-1],[frameRight,frameBottom,-1,-1]].forEach(([x,y,sx,sy])=>{
        ctx.beginPath();ctx.moveTo(x+sx*corner,y);ctx.lineTo(x,y);ctx.lineTo(x,y+sy*corner);ctx.stroke();
      });

      // accumulated dwell, additively blended so the fixated spot burns brightest
      ctx.save();
      ctx.beginPath();ctx.rect(frameLeft,frameTop,frameWidth,frameHeight);ctx.clip();
      ctx.globalCompositeOperation="lighter";
      spots.forEach(([x,y,weight],index)=>{
        const hot=index===live?1.35:1;
        const radius=frameHeight*(.26+weight*.20)*hot;
        const gradient=ctx.createRadialGradient(x,y,0,x,y,radius);
        gradient.addColorStop(0,`rgba(255,240,196,${.5*weight*heat*hot})`);
        gradient.addColorStop(.34,`rgba(255,150,62,${.34*weight*heat})`);
        gradient.addColorStop(.7,`rgba(214,64,72,${.15*weight*heat})`);
        gradient.addColorStop(1,"rgba(120,32,96,0)");
        ctx.fillStyle=gradient;ctx.beginPath();ctx.arc(x,y,radius,0,Math.PI*2);ctx.fill();
      });
      ctx.globalCompositeOperation="source-over";
      ctx.restore();

      // fixation rings, sized by dwell
      spots.forEach(([x,y,weight],index)=>{
        const hot=index===live;
        ctx.beginPath();ctx.arc(x,y,3.4+weight*2.6,0,Math.PI*2);
        ctx.strokeStyle=hot?`rgba(255,236,190,${selected?.95:.55})`:`rgba(255,169,92,${selected?.5:.28})`;
        ctx.lineWidth=hot?1.6:1;ctx.stroke();
      });

      const target=spots[live];
      // the eye itself: lid almond, iris tracking the live spot, pupil
      const look=Math.max(-1,Math.min(1,(target[1]-eyeY)/(height*.5)));
      const irisX=eyeX+eyeW*.34,irisY=eyeY+look*eyeH*.26;
      ctx.strokeStyle=selected?"#eaf2ff":"#a3b9d8";ctx.lineWidth=1.4;ctx.lineJoin="round";
      ctx.beginPath();
      ctx.moveTo(eyeX-eyeW,eyeY);
      ctx.quadraticCurveTo(eyeX,eyeY-eyeH,eyeX+eyeW,eyeY);
      ctx.quadraticCurveTo(eyeX,eyeY+eyeH,eyeX-eyeW,eyeY);
      ctx.stroke();
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(eyeX-eyeW,eyeY);
      ctx.quadraticCurveTo(eyeX,eyeY-eyeH,eyeX+eyeW,eyeY);
      ctx.quadraticCurveTo(eyeX,eyeY+eyeH,eyeX-eyeW,eyeY);
      ctx.clip();
      ctx.beginPath();ctx.arc(irisX,irisY,eyeH*.66,0,Math.PI*2);
      ctx.strokeStyle=selected?"#4ea8ff":"#7aa8eb";ctx.lineWidth=1.2;ctx.stroke();
      ctx.beginPath();ctx.arc(irisX,irisY,eyeH*.26,0,Math.PI*2);
      ctx.fillStyle=selected?"#eaf2ff":"#a3b9d8";ctx.fill();
      ctx.restore();

      // gaze ray from the pupil to whatever it is resting on
      ctx.strokeStyle=`rgba(255,214,150,${selected?.55:.28})`;ctx.lineWidth=1;
      ctx.setLineDash([3,4]);
      ctx.beginPath();ctx.moveTo(irisX+eyeH*.5,irisY);ctx.lineTo(target[0],target[1]);ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
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
    /* Same pose input as `action`, read a different way: the frozen adapter keeps 17 of the 33
       points and only ever sees fixed sampled windows. So this skeleton is deliberately NOT the
       one on the action card — amber instead of blue, diamond joints instead of round, echoes of
       the earlier frames still inside the window, and the sampled-frame strip underneath. */
    const centerX=width/2,top=height*.05,scale=height*.126;
    const pose=moment=>{
      const sway=Math.sin(moment*1.9),counter=Math.cos(moment*1.9);
      return {
        nose:[centerX,top+scale*.32],
        eyeL:[centerX-scale*.13,top+scale*.21],eyeR:[centerX+scale*.13,top+scale*.21],
        earL:[centerX-scale*.26,top+scale*.28],earR:[centerX+scale*.26,top+scale*.28],
        shL:[centerX-scale*.52,top+scale*.95],shR:[centerX+scale*.52,top+scale*.95],
        elL:[centerX-scale*.80+sway*scale*.14,top+scale*1.55],
        elR:[centerX+scale*.80-sway*scale*.14,top+scale*1.55],
        wrL:[centerX-scale*.92+sway*scale*.30,top+scale*2.15],
        wrR:[centerX+scale*.92-sway*scale*.30,top+scale*2.15],
        hipL:[centerX-scale*.34,top+scale*2.05],hipR:[centerX+scale*.34,top+scale*2.05],
        knL:[centerX-scale*.40+counter*scale*.16,top+scale*2.90],
        knR:[centerX+scale*.40-counter*scale*.16,top+scale*2.90],
        anL:[centerX-scale*.44+counter*scale*.30,top+scale*3.70],
        anR:[centerX+scale*.44-counter*scale*.30,top+scale*3.70]
      };
    };
    const bones=[["shL","shR"],["shL","elL"],["elL","wrL"],["shR","elR"],["elR","wrR"],
      ["shL","hipL"],["shR","hipR"],["hipL","hipR"],["hipL","knL"],["knL","anL"],
      ["hipR","knR"],["knR","anR"],["nose","eyeL"],["nose","eyeR"],["eyeL","earL"],["eyeR","earR"]];
    const draw=(points,color,lineWidth)=>{
      ctx.strokeStyle=color;ctx.lineWidth=lineWidth;
      bones.forEach(([a,b])=>{ctx.beginPath();ctx.moveTo(...points[a]);ctx.lineTo(...points[b]);ctx.stroke();});
    };
    ctx.save();
    ctx.lineCap="butt";ctx.lineJoin="miter";
    // earlier frames of the same window, fading back
    for(let back=3;back>=1;back--){
      draw(pose(time-back*.34),`rgba(255,169,92,${(selected?.13:.07)/back})`,1);
    }
    const points=pose(time);
    draw(points,selected?"#ffc07a":"#b08055",1.5);
    Object.entries(points).forEach(([name,[x,y]])=>{
      const head=["nose","eyeL","eyeR","earL","earR"].includes(name),size=head?1.7:2.6;
      ctx.save();ctx.translate(x,y);ctx.rotate(Math.PI/4);
      ctx.fillStyle="#0d1a2e";ctx.fillRect(-size,-size,size*2,size*2);
      ctx.strokeStyle=head?(selected?"#4ea8ff":"#3c6fa8"):(selected?"#ffc07a":"#b08055");
      ctx.lineWidth=1.2;ctx.strokeRect(-size,-size,size*2,size*2);
      ctx.restore();
    });
    // sampled-frame strip: the fixed window sliding by its fixed stride
    const stripWidth=Math.min(width*.62,150),stripLeft=centerX-stripWidth/2,stripY=height*.70;
    const frames=24,windowSize=8,step=stripWidth/(frames-1);
    const start=Math.floor(time*.8)%(frames-windowSize+1);
    for(let index=0;index<frames;index++){
      const inside=index>=start&&index<start+windowSize;
      const x=stripLeft+index*step;
      ctx.strokeStyle=inside?(selected?"#ffc07a":"#b08055")
        :(selected?"rgba(78,168,255,.32)":"rgba(122,168,235,.18)");
      ctx.lineWidth=inside?1.4:1;
      ctx.beginPath();ctx.moveTo(x,stripY-(inside?4.5:2.5));ctx.lineTo(x,stripY+(inside?4.5:2.5));ctx.stroke();
    }
    ctx.strokeStyle=selected?"rgba(255,192,122,.65)":"rgba(176,128,85,.4)";ctx.lineWidth=1;
    const windowLeft=stripLeft+start*step,windowRight=windowLeft+(windowSize-1)*step;
    ctx.beginPath();
    ctx.moveTo(windowLeft,stripY+8);ctx.lineTo(windowLeft,stripY+11);
    ctx.lineTo(windowRight,stripY+11);ctx.lineTo(windowRight,stripY+8);ctx.stroke();
    ctx.restore();
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
    state.slots=pickSlots();
    const elements=document.querySelectorAll("#mods .mod");
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
  }
  window.GBADFTheme={
    change(theme){if(theme==="console")start();else stop();},
    step(step){state.step=step;if(step===1)layoutHitZones();if(step===4)emitPipeline();},
    refresh(){layoutHitZones();}
  };
  addEventListener("resize",resize);
  if(document.documentElement.dataset.theme==="console")start();
})();
