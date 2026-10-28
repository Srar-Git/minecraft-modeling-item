(function (host) {
  function create(spec) {
    spec=structuredClone(spec);
    const finite = n => typeof n === 'number' && Number.isFinite(n);
    const vec = v => Array.isArray(v) && v.length === 3 && v.every(finite);
    if (!host.Project || Project.uuid !== spec.project_id) throw Error('Selected project mismatch');
    if (!Array.isArray(spec.tracks) || !spec.tracks.length) throw Error('Nonempty tracks required');
    const used = new Set();
    for (const t of spec.tracks) {
      if (!['rotate','translate'].includes(t.kind) || !Array.isArray(t.element_ids) || !t.element_ids.length || !vec(t.axis) || !t.axis.some(n=>n!==0) || !vec(t.pivot || [0,0,0]) || !finite(t.period) || t.period <= 0 || !finite(t.amplitude) || !finite(t.phase ?? 0) || !finite(t.offset ?? 0)) throw Error('Invalid motion track');
      for (const id of t.element_ids) {
        if (used.has(id) || !Cube.all.some(c=>c.uuid===id)) throw Error('Duplicate or missing cube UUID');
        used.add(id);
      }
    }
    const owner = Project;
    let records = [], timer = null, mode = null, undo = null, epoch = 0, disposed = false;
    function restore() {
      for (const r of records) {
        r.mesh.matrix.copy(r.local);
        r.mesh.matrix.decompose(r.mesh.position,r.mesh.quaternion,r.mesh.scale);
        r.mesh.matrixAutoUpdate=r.auto;
        r.mesh.updateMatrixWorld(true);
      }
      records=[];
    }
    function bind() {
      restore();
      if (Project !== owner) throw Error('Project switched; stop this preview');
      owner.model_3d.updateWorldMatrix(true,true);
      const inv=owner.model_3d.matrixWorld.clone().invert();
      const pending=[];
      for (const t of spec.tracks) for (const id of t.element_ids) {
        const cube=Cube.all.find(c=>c.uuid===id);
        if (!cube?.mesh) throw Error('Cube disappeared; rebind from a new specification');
        const mesh=cube.mesh; mesh.updateWorldMatrix(true,false);
        pending.push({id,mesh,track:t,local:mesh.matrix.clone(),base:inv.clone().multiply(mesh.matrixWorld),auto:mesh.matrixAutoUpdate});
      }
      records=pending;
      for(const r of records) r.mesh.matrixAutoUpdate=false;
      mode=Modes.selected.id;undo=Undo.index;
    }
    function pose(seconds) {
      if (disposed || !finite(seconds)) throw Error('Disposed preview or invalid time');
      if(Project !== owner) { stop(); throw Error('Project changed'); }
      if(!['edit','display'].includes(Modes.selected.id)) { stop(); throw Error('Preview requires Edit or Display'); }
      if(records.length && Undo.index!==undo) { stop(); throw Error('Source edited; create a new preview baseline'); }
      if(!records.length || mode!==Modes.selected.id) bind();
      owner.model_3d.updateWorldMatrix(true,true);
      const transforms = new Map();
      for (const t of spec.tracks) {
        const value=(t.offset??0)+t.amplitude*Math.sin(2*Math.PI*(seconds/t.period+(t.phase??0)));
        const axis=new THREE.Vector3(...t.axis).normalize();
        let transform=new THREE.Matrix4();
        if(t.kind==='translate') transform.makeTranslation(axis.x*value,axis.y*value,axis.z*value);
        else {
          const p=t.pivot||[0,0,0];
          transform.makeTranslation(...p).multiply(new THREE.Matrix4().makeRotationAxis(axis,value*Math.PI/180)).multiply(new THREE.Matrix4().makeTranslation(...p.map(n=>-n)));
        }
        transforms.set(t,transform);
      }
      for (const r of records) {
        r.mesh.parent.updateWorldMatrix(true,false);
        const local=r.mesh.parent.matrixWorld.clone().invert().multiply(owner.model_3d.matrixWorld).multiply(transforms.get(r.track)).multiply(r.base);
        r.mesh.matrix.copy(local);r.mesh.matrix.decompose(r.mesh.position,r.mesh.quaternion,r.mesh.scale);r.mesh.updateMatrixWorld(true);
      }
      return sample(seconds);
    }
    function sample(seconds) {
      owner.model_3d.updateWorldMatrix(true,true);
      const inv=owner.model_3d.matrixWorld.clone().invert();
      return {time:seconds,mode:Modes.selected.id,elements:Object.fromEntries(records.map(r=>[r.id,inv.clone().multiply(r.mesh.matrixWorld).toArray()]))};
    }
    function stop() { if(timer!==null) clearInterval(timer); timer=null;restore(); }
    function start() {
      if(disposed) throw Error('Disposed preview');
      stop();epoch=performance.now();pose(0);
      timer=setInterval(()=>{
        try {
          if(Project!==owner || Outliner.selected.length || !['edit','display'].includes(Modes.selected.id)) { stop();return; }
          pose((performance.now()-epoch)/1000);
        } catch(e) { stop(); Blockbench.showQuickMessage('Item preview stopped: '+e.message); }
      },33);
    }
    return {pose,start,stop,dispose(){stop();disposed=true;},sample, status(){return {project_id:owner.uuid,running:timer!==null,tracked:records.length,mode,render_only:true};}};
  }
  host.MinecraftItemPreviewFactory = {create,version:1};
})(globalThis);
