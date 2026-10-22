// A bendy low-poly limb: a tapered tube along a smooth curve through three points (root, joint, end),
// rebuilt in place every frame. Replaces two straight cylinders and a joint ball, so elbows and knees
// read as one flexible stroke (the classic stickman look) instead of robot segments.
import * as THREE from "three";

const _v = new THREE.Vector3(), _n = new THREE.Vector3(), _b = new THREE.Vector3(), _t = new THREE.Vector3();

export class Tube {
  constructor(material, radial = 6, segs = 12) {
    this.radial = radial;
    this.segs = segs;
    const ringVerts = (segs + 1) * radial;
    const pos = new Float32Array((ringVerts + 2) * 3);
    const idx = [];
    for (let i = 0; i < segs; i++) {
      for (let j = 0; j < radial; j++) {
        const a = i * radial + j, b = i * radial + ((j + 1) % radial), c = a + radial, d = b + radial;
        idx.push(a, c, b, b, c, d);
      }
    }
    const capA = ringVerts, capB = ringVerts + 1;
    for (let j = 0; j < radial; j++) {
      idx.push(capA, j, (j + 1) % radial);
      idx.push(capB, segs * radial + ((j + 1) % radial), segs * radial + j);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setIndex(idx);
    this.geo = geo;
    this.mesh = new THREE.Mesh(geo, material);
    this.mesh.castShadow = true;
    this.mesh.frustumCulled = false;
    this.pts = Array.from({ length: segs + 1 }, () => new THREE.Vector3());
  }

  /**
   * Limb p0 -> p1 -> p2: two straight parts joined by a rounded bend at p1 (a fillet), so a joint reads as
   * soft and flexible however far it bends, without the overshoot of a curve forced through p1.
   * Radius r0 at the root tapering to r2.
   */
  update(p0, p1, p2, r0, r2, ref = new THREE.Vector3(0, 0, 1), round = 0.42) {
    const { segs, radial, pts } = this;
    const d1 = p1.clone().sub(p0), d2 = p2.clone().sub(p1);
    const l1 = d1.length(), l2 = d2.length();
    d1.normalize(); d2.normalize();
    const rr = round * Math.min(l1, l2);
    const A = p1.clone().addScaledVector(d1, -rr), B = p1.clone().addScaledVector(d2, rr);
    // fixed vertex budget: a quarter on each straight part, half on the bend
    const n1 = Math.max(1, Math.floor(segs / 4)), n3 = n1, n2 = segs - n1 - n3;
    let k = 0;
    for (let i = 0; i < n1; i++) pts[k++].copy(p0).lerp(A, i / n1);
    for (let i = 0; i < n2; i++) {
      const s = i / n2, u = 1 - s;
      pts[k++].set(0, 0, 0).addScaledVector(A, u * u).addScaledVector(p1, 2 * u * s).addScaledVector(B, s * s);
    }
    for (let i = 0; i <= n3; i++) pts[k++].copy(B).lerp(p2, i / n3);
    const pos = this.geo.attributes.position.array;
    // parallel-transport frame: no twisting along the limb
    _t.copy(pts[1]).sub(pts[0]).normalize();
    _n.copy(ref).addScaledVector(_t, -ref.dot(_t));
    if (_n.lengthSq() < 1e-6) _n.set(1, 0, 0).addScaledVector(_t, -_t.x);
    _n.normalize();
    for (let i = 0; i <= segs; i++) {
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(segs, i + 1)];
      _t.copy(b).sub(a).normalize();
      _n.addScaledVector(_t, -_n.dot(_t)).normalize();
      _b.crossVectors(_t, _n);
      const s = i / segs;
      const r = r0 + (r2 - r0) * s;
      for (let j = 0; j < radial; j++) {
        const th = (j / radial) * Math.PI * 2;
        _v.copy(pts[i]).addScaledVector(_n, Math.cos(th) * r).addScaledVector(_b, Math.sin(th) * r);
        pos.set([_v.x, _v.y, _v.z], (i * radial + j) * 3);
      }
    }
    const ring = (segs + 1) * radial;
    pos.set([pts[0].x, pts[0].y, pts[0].z], ring * 3);
    pos.set([pts[segs].x, pts[segs].y, pts[segs].z], (ring + 1) * 3);
    this.geo.attributes.position.needsUpdate = true;
  }
}
