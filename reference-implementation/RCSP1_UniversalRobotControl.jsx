/**
 * ╔══════════════════════════════════════════════════════════════════════╗
 * ║  RCSP-1  —  Robot Control Standard Profile, Version 1.0             ║
 * ║  A universal web-based teleoperation interface standard              ║
 * ║  covering 9 robot morphology categories.                             ║
 * ║                                                                      ║
 * ║  Analogous to: RFC 791 (IP), RFC 2616 (HTTP), MIDI 1.0              ║
 * ║  Transport: ROS2 geometry_msgs/Twist, sensor_msgs/Joy, MQTT          ║
 * ║  URDF Extension: <rcsp version="1.0"> block (see spec below)         ║
 * ║                                                                      ║
 * ║  Categories defined in RCSP-1:                                       ║
 * ║    1. wheeled        — differential/omni/tracked base                ║
 * ║    2. legged         — quadruped / hexapod (no arms)                 ║
 * ║    3. loco_manip     — legged base + arm(s)                          ║
 * ║    4. wheeled_humanoid — wheeled base + full upper body              ║
 * ║    5. full_humanoid  — bipedal + full upper body                     ║
 * ║    6. manipulator    — fixed arm, no base                            ║
 * ║    7. aerial         — drone / VTOL / multirotor                     ║
 * ║    8. marine_surface — USV / ASV surface vessel                      ║
 * ║    9. marine_sub     — ROV / AUV underwater vehicle                  ║
 * ║                                                                      ║
 * ║  URDF RCSP-1 block example:                                          ║
 * ║  ─────────────────────────────────────────────────────────────────  ║
 * ║  <rcsp version="1.0">                                                ║
 * ║    <category>quadruped</category>  <!-- RCSP-1 category id -->       ║
 * ║    <display_name>Unitree Go2</display_name>                          ║
 * ║    <capabilities>                                                    ║
 * ║      <locomotion axes="vx vy wz"                                     ║
 * ║                  max_vx="1.5" max_vy="0" max_wz="2.0"/>             ║
 * ║      <gait modes="stand trot bound crawl prone"/>                    ║
 * ║      <body_pose pitch="true" roll="true" height="true"/>             ║
 * ║      <estop required="true"/>                                        ║
 * ║    </capabilities>                                                   ║
 * ║    <telemetry>                                                       ║
 * ║      <field id="battery" unit="%" warn_below="20"/>                  ║
 * ║      <field id="temp"    unit="C"  warn_above="55"/>                 ║
 * ║      <field id="voltage" unit="V"/>                                  ║
 * ║      <field id="speed"   unit="m/s"/>                                ║
 * ║    </telemetry>                                                      ║
 * ║    <transport>                                                       ║
 * ║      <ros2 cmd_vel="/cmd_vel" joy="/joy"                             ║
 * ║            sport_mode="/api/sport/request"/>                         ║
 * ║      <mqtt topic_prefix="/robot/go2"                                 ║
 * ║             broker="${MQTT_BROKER}"/>                                ║
 * ║    </transport>                                                      ║
 * ║  </rcsp>                                                             ║
 * ║                                                                      ║
 * ║  Wire format (RCSP-1 JSON over MQTT / WebSocket):                   ║
 * ║  { "rcsp":"1.0", "type":"cmd",                                       ║
 * ║    "lx":0.0,"ly":0.0,"rx":0.0,"ry":0.0,                            ║
 * ║    "speed":0.5, "mode":"trot", "estop":false,                       ║
 * ║    "ts":1719000000000 }                                              ║
 * ║                                                                      ║
 * ║  ROS2 Twist mapping:                                                 ║
 * ║    linear.x  = lx * max_vx                                           ║
 * ║    linear.y  = ly * max_vy  (omni/aerial only)                       ║
 * ║    linear.z  = ry * max_vz  (aerial/sub only)                        ║
 * ║    angular.z = rx * max_wz                                           ║
 * ╚══════════════════════════════════════════════════════════════════════╝
 */

import { useState, useEffect, useRef, useCallback } from "react";

// ─── RCSP-1 Category Registry ────────────────────────────────────────────────
const RCSP_CATEGORIES = {
  wheeled: {
    id: "wheeled",
    label: "Wheeled / Tracked",
    icon: "⊙",
    color: "#00d4ff",
    description: "Differential drive · Omni · Tracked",
    examples: "TurtleBot · Clearpath Husky · Boston Dynamics Stretch base",
    leftStick:  { label: "DRIVE", axes: ["vx","wz"] },
    rightStick: null,
    modes: ["IDLE","DRIVE","TURBO","DOCK"],
    actions: ["HOME","STOP"],
    telem: ["battery","temp","speed","wifi"],
    bodyPose: false,
    hasArm: false,
    hasAltitude: false,
    hasDepth: false,
    ros2: { cmd_vel: "/cmd_vel" },
    twist: { lx:"linear.x", rx:"angular.z" },
  },
  legged: {
    id: "legged",
    label: "Legged (Quadruped/Hexapod)",
    icon: "⬡",
    color: "#00d4ff",
    description: "4-leg · 6-leg · No arms",
    examples: "Unitree Go2 · Boston Dynamics Spot · ANYmal · MIT Mini Cheetah",
    leftStick:  { label: "MOVE", axes: ["vx","vy"] },
    rightStick: { label: "POSE", axes: ["pitch","height"] },
    modes: ["STAND","TROT","BOUND","CRAWL","PRONE"],
    actions: ["SIT","LIE","ROLL"],
    telem: ["battery","temp","voltage","speed"],
    bodyPose: true,
    hasArm: false,
    hasAltitude: false,
    hasDepth: false,
    ros2: { cmd_vel: "/cmd_vel", sport: "/api/sport/request" },
    twist: { lx:"linear.x", ly:"linear.y", rx:"angular.z" },
  },
  loco_manip: {
    id: "loco_manip",
    label: "Loco-Manipulation",
    icon: "⬡⌇",
    color: "#a78bfa",
    description: "Legged base + arm(s)",
    examples: "Spot + Arm · Go2 + Z1 · ANYmal + ARM",
    leftStick:  { label: "DRIVE", axes: ["vx","wz"] },
    rightStick: { label: "ARM EE", axes: ["ee_x","ee_z"] },
    modes: ["WALK","MANIPULATE","LOCO-MANIP","STAND"],
    actions: ["GRIP","RELEASE","STOW","HOME"],
    telem: ["battery","temp","payload","speed"],
    bodyPose: false,
    hasArm: true,
    hasAltitude: false,
    hasDepth: false,
    ros2: { cmd_vel: "/cmd_vel", arm: "/arm/cmd_ee" },
    twist: { lx:"linear.x", rx:"angular.z" },
  },
  wheeled_humanoid: {
    id: "wheeled_humanoid",
    label: "Wheeled Humanoid",
    icon: "♟",
    color: "#f59e0b",
    description: "Wheeled base + full upper body",
    examples: "Sanctuary Phoenix Gen8 · Apollo · Apptronik",
    leftStick:  { label: "BASE", axes: ["vx","wz"] },
    rightStick: { label: "TORSO", axes: ["yaw","pitch"] },
    modes: ["DRIVE","REACH","BIMANUAL","IDLE"],
    actions: ["GRIP-L","GRIP-R","WAVE","HOME"],
    telem: ["battery","temp","payload","balance"],
    bodyPose: false,
    hasArm: true,
    hasAltitude: false,
    hasDepth: false,
    ros2: { cmd_vel: "/cmd_vel", torso: "/torso/cmd", arm: "/arm/cmd_ee" },
    twist: { lx:"linear.x", rx:"angular.z" },
  },
  full_humanoid: {
    id: "full_humanoid",
    label: "Full Humanoid (Bipedal)",
    icon: "⬆",
    color: "#00d4ff",
    description: "Legged locomotion + full upper body",
    examples: "Unitree G1/H1 · Figure 02 · Tesla Optimus · Boston Dynamics Atlas",
    leftStick:  { label: "WALK", axes: ["vx","vy"] },
    rightStick: { label: "TURN/LOOK", axes: ["wz","head_pitch"] },
    modes: ["STAND","WALK","JOG","MANIPULATE","DANCE"],
    actions: ["GRIP-L","GRIP-R","WAVE","SIT","HOME"],
    telem: ["battery","temp","balance","speed"],
    bodyPose: true,
    hasArm: true,
    hasAltitude: false,
    hasDepth: false,
    ros2: { cmd_vel: "/cmd_vel", wholebody: "/wholebody/cmd" },
    twist: { lx:"linear.x", ly:"linear.y", rx:"angular.z" },
  },
  manipulator: {
    id: "manipulator",
    label: "Fixed Manipulator (Arm)",
    icon: "⌇",
    color: "#10b981",
    description: "Stationary arm · 6-DOF · No base",
    examples: "UR5/10 · Piper AgileX · Franka · Kinova · ABB",
    leftStick:  { label: "EE XYZ", axes: ["ee_x","ee_y"] },
    rightStick: { label: "EE RPY", axes: ["roll","pitch"] },
    modes: ["JOINT","CARTESIAN","TEACH","REPLAY"],
    actions: ["GRIP","RELEASE","HOME","ZERO"],
    telem: ["temp","payload","ee_pos","joint_torque"],
    bodyPose: false,
    hasArm: true,
    hasAltitude: false,
    hasDepth: false,
    ros2: { arm: "/arm/cmd_ee", joint: "/arm/cmd_joint" },
    twist: { lx:"linear.x", ly:"linear.y", rx:"angular.z", ry:"linear.z" },
  },
  aerial: {
    id: "aerial",
    label: "Aerial (Drone / VTOL)",
    icon: "✦",
    color: "#f43f5e",
    description: "Multirotor · Fixed-wing · VTOL",
    examples: "DJI · ArduPilot · PX4 · Custom UAV",
    leftStick:  { label: "THROTTLE/YAW", axes: ["vz","wz"] },
    rightStick: { label: "PITCH/ROLL", axes: ["vx","vy"] },
    modes: ["STABILIZE","ALTITUDE","LOITER","AUTO","RTL"],
    actions: ["ARM","TAKEOFF","LAND","RTH"],
    telem: ["battery","altitude","speed","gps","rssi"],
    bodyPose: false,
    hasArm: false,
    hasAltitude: true,
    hasDepth: false,
    ros2: { cmd_vel: "/cmd_vel", mavros: "/mavros/setpoint_velocity/cmd_vel" },
    twist: { lx:"linear.z", rx:"angular.z", ry:"linear.x", rx2:"linear.y" },
  },
  marine_surface: {
    id: "marine_surface",
    label: "Marine Surface (USV)",
    icon: "〜",
    color: "#0ea5e9",
    description: "Unmanned surface vessel · ASV · Boat",
    examples: "ArduPilot Boat · WAM-V · Custom USV",
    leftStick:  { label: "THROTTLE", axes: ["vx","vy"] },
    rightStick: { label: "HEADING", axes: ["wz","null"] },
    modes: ["MANUAL","HOLD","AUTO","LOITER"],
    actions: ["ANCHOR","RETURN","LIGHT","HORN"],
    telem: ["battery","heading","speed","depth","gps"],
    bodyPose: false,
    hasArm: false,
    hasAltitude: false,
    hasDepth: false,
    ros2: { cmd_vel: "/cmd_vel" },
    twist: { lx:"linear.x", rx:"angular.z" },
  },
  marine_sub: {
    id: "marine_sub",
    label: "Marine Underwater (ROV/AUV)",
    icon: "▽",
    color: "#6366f1",
    description: "ROV · AUV · Underwater vehicle",
    examples: "BlueROV2 · VideoRay · Custom ROV",
    leftStick:  { label: "SURGE/DEPTH", axes: ["vx","vz"] },
    rightStick: { label: "YAW/SWAY", axes: ["wz","vy"] },
    modes: ["MANUAL","DEPTH HOLD","STABILIZE","AUTO"],
    actions: ["LIGHTS","GRIPPER","SURFACE","ZERO"],
    telem: ["battery","depth","heading","temp","pressure"],
    bodyPose: false,
    hasArm: false,
    hasAltitude: false,
    hasDepth: true,
    ros2: { cmd_vel: "/cmd_vel", lights: "/lights/cmd" },
    twist: { lx:"linear.x", ly:"linear.y", lx2:"linear.z", rx:"angular.z" },
  },
};

// ─── Styles ───────────────────────────────────────────────────────────────────
const STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@600;700&display=swap');
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:#060a0f;}

  .rcsp-root{
    min-height:100vh;
    background:#060a0f;
    color:#c8d8e8;
    font-family:'Barlow',sans-serif;
    font-size:13px;
    display:flex;
    flex-direction:column;
    align-items:center;
    padding:12px;
    gap:10px;
  }

  /* ── HEADER ── */
  .rcsp-header{
    width:100%;max-width:1200px;
    display:flex;align-items:center;justify-content:space-between;
    border-bottom:1px solid #0f1e2d;
    padding-bottom:10px;
  }
  .rcsp-wordmark{
    display:flex;flex-direction:column;gap:1px;
  }
  .rcsp-title{
    font-family:'Barlow Condensed',sans-serif;
    font-size:20px;font-weight:700;letter-spacing:3px;
    color:#00d4ff;text-transform:uppercase;
  }
  .rcsp-subtitle{
    font-family:'Share Tech Mono',monospace;
    font-size:9px;color:#2a4a60;letter-spacing:2px;
  }
  .rcsp-meta{
    display:flex;gap:16px;
    font-family:'Share Tech Mono',monospace;font-size:10px;color:#2a4a60;
  }
  .rcsp-meta .v{color:#00d4ff88;}
  .rcsp-meta .ok{color:#10b981;}

  /* ── CATEGORY SELECTOR ── */
  .rcsp-selector{
    width:100%;max-width:1200px;
    display:flex;flex-direction:column;gap:8px;
  }
  .rcsp-selector-label{
    font-family:'Share Tech Mono',monospace;font-size:9px;
    color:#2a4a60;letter-spacing:2px;text-transform:uppercase;
  }
  .rcsp-cats{
    display:flex;flex-wrap:wrap;gap:6px;
  }
  .rcsp-cat-btn{
    display:flex;align-items:center;gap:6px;
    padding:6px 12px;
    background:#0a1520;
    border:1px solid #0f1e2d;
    border-radius:3px;
    color:#3a5a70;
    font-family:'Barlow Condensed',sans-serif;
    font-size:12px;font-weight:600;letter-spacing:1px;
    cursor:pointer;
    transition:all 0.15s;
    text-transform:uppercase;
  }
  .rcsp-cat-btn:hover{border-color:#00d4ff44;color:#7a9aaa;}
  .rcsp-cat-btn.active{
    background:#00d4ff0d;
    border-color:currentColor;
    color:var(--cat-color,#00d4ff);
  }
  .rcsp-cat-icon{font-size:14px;}

  /* ── MAIN PANEL ── */
  .rcsp-panel{
    width:100%;max-width:1200px;
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:10px;
  }

  /* ── SHARED CORE (left column) ── */
  .rcsp-core{
    background:#0a1218;
    border:1px solid #0f1e2d;
    border-radius:4px;
    display:flex;flex-direction:column;
    overflow:hidden;
  }

  /* ── CATEGORY PANEL (right column) ── */
  .rcsp-catpanel{
    background:#0a1218;
    border:1px solid #0f1e2d;
    border-radius:4px;
    display:flex;flex-direction:column;
    overflow:hidden;
  }

  /* ── SECTION HEADER ── */
  .rcsp-sec-hdr{
    display:flex;align-items:center;gap:10px;
    padding:10px 14px;
    background:#060a0f;
    border-bottom:1px solid #0f1e2d;
  }
  .rcsp-sec-title{
    font-family:'Barlow Condensed',sans-serif;
    font-size:13px;font-weight:700;letter-spacing:2px;
    text-transform:uppercase;color:#4a7a8a;
  }
  .rcsp-sec-badge{
    margin-left:auto;
    font-family:'Share Tech Mono',monospace;
    font-size:9px;color:#1a3a4a;letter-spacing:1px;
  }

  /* ── CONNECTION ROW ── */
  .rcsp-conn-row{
    display:flex;align-items:center;gap:10px;
    padding:8px 14px;
    border-bottom:1px solid #0f1e2d;
  }
  .rcsp-conn-dot{
    width:7px;height:7px;border-radius:50%;
    background:#10b981;
    box-shadow:0 0 6px #10b981;
    flex-shrink:0;
  }
  .rcsp-conn-dot.off{background:#ef4444;box-shadow:none;}
  .rcsp-conn-name{
    font-family:'Barlow Condensed',sans-serif;
    font-size:15px;font-weight:700;letter-spacing:1px;
    color:var(--cat-color,#00d4ff);
    flex:1;
  }
  .rcsp-conn-sub{
    font-family:'Share Tech Mono',monospace;
    font-size:9px;color:#2a4a60;
  }
  .rcsp-conn-toggle{
    padding:4px 10px;
    background:#060a0f;
    border:1px solid #0f1e2d;
    border-radius:2px;
    color:#3a5a70;
    font-family:'Share Tech Mono',monospace;
    font-size:9px;letter-spacing:1px;
    cursor:pointer;
    transition:all 0.15s;
  }
  .rcsp-conn-toggle:hover{border-color:#00d4ff44;color:#6a8a9a;}

  /* ── TELEMETRY ── */
  .rcsp-telem{
    display:flex;justify-content:space-around;
    padding:8px 10px;
    background:#060a0f;
    border-bottom:1px solid #0f1e2d;
  }
  .rcsp-tel-item{display:flex;flex-direction:column;align-items:center;gap:2px;}
  .rcsp-tel-val{
    font-family:'Share Tech Mono',monospace;
    font-size:14px;color:#c8d8e8;
  }
  .rcsp-tel-val.good{color:#10b981;}
  .rcsp-tel-val.warn{color:#f59e0b;}
  .rcsp-tel-val.bad{color:#ef4444;}
  .rcsp-tel-lbl{
    font-family:'Share Tech Mono',monospace;
    font-size:8px;color:#2a4a60;letter-spacing:1px;
  }

  /* ── ESTOP ── */
  .rcsp-estop-wrap{padding:8px 14px;border-bottom:1px solid #0f1e2d;}
  .rcsp-estop{
    width:100%;padding:8px;
    background:#1a0808;
    border:1px solid #ef444466;
    border-radius:3px;
    color:#ef4444;
    font-family:'Barlow Condensed',sans-serif;
    font-size:14px;font-weight:700;letter-spacing:3px;
    cursor:pointer;
    transition:all 0.1s;
    text-transform:uppercase;
  }
  .rcsp-estop:hover{background:#2a0a0a;border-color:#ef4444;box-shadow:0 0 12px #ef444433;}
  .rcsp-estop.active{background:#ef4444;color:#fff;box-shadow:0 0 20px #ef4444;}

  /* ── SPEED ── */
  .rcsp-speed-row{
    display:flex;align-items:center;gap:10px;
    padding:8px 14px;border-bottom:1px solid #0f1e2d;
    font-family:'Share Tech Mono',monospace;font-size:9px;color:#2a4a60;
  }
  .rcsp-slider{
    -webkit-appearance:none;flex:1;height:2px;
    background:#0f1e2d;border-radius:1px;outline:none;cursor:pointer;
  }
  .rcsp-slider::-webkit-slider-thumb{
    -webkit-appearance:none;width:12px;height:12px;
    border-radius:50%;background:var(--cat-color,#00d4ff);
    box-shadow:0 0 6px var(--cat-color,#00d4ff);cursor:pointer;
  }
  .rcsp-speed-val{color:var(--cat-color,#00d4ff);min-width:28px;text-align:right;}

  /* ── JOYSTICK AREA ── */
  .rcsp-sticks{
    display:flex;justify-content:space-around;align-items:center;
    padding:12px 14px;flex:1;gap:8px;
  }
  .stick-wrap{display:flex;flex-direction:column;align-items:center;gap:4px;}
  .stick-lbl{
    font-family:'Share Tech Mono',monospace;font-size:8px;
    color:#1a3a4a;letter-spacing:1px;text-transform:uppercase;
  }
  .stick-outer{
    width:84px;height:84px;
    background:#060a0f;
    border:1px solid #0f1e2d;
    border-radius:50%;
    position:relative;cursor:crosshair;touch-action:none;
  }
  .stick-outer::after{
    content:'';position:absolute;top:50%;left:50%;
    transform:translate(-50%,-50%);
    width:56%;height:56%;
    border:1px solid #0f1e2d;border-radius:50%;
  }
  .stick-knob{
    position:absolute;width:26px;height:26px;
    background:radial-gradient(circle at 40% 35%,#1a3050,#060a0f);
    border:1px solid var(--cat-color,#00d4ff);
    border-radius:50%;
    transform:translate(-50%,-50%);
    box-shadow:0 0 10px var(--cat-color,#00d4ff)44;
    cursor:grab;
    transition:box-shadow 0.1s;
  }
  .stick-vals{
    font-family:'Share Tech Mono',monospace;font-size:8px;color:#1a3a4a;
  }
  .stick-vals span{color:var(--cat-color,#00d4ff)88;}
  .stick-placeholder{
    width:84px;height:84px;
    border:1px dashed #0f1e2d;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    font-family:'Share Tech Mono',monospace;font-size:8px;color:#1a2a3a;
    letter-spacing:1px;
  }

  /* ── WIRE FORMAT MONITOR ── */
  .rcsp-wire{
    margin:0 14px 10px;
    background:#060a0f;
    border:1px solid #0f1e2d;
    border-radius:3px;
    padding:8px 10px;
    font-family:'Share Tech Mono',monospace;
    font-size:9px;color:#2a4a60;
    line-height:1.6;
  }
  .rcsp-wire .k{color:#3a6a7a;}
  .rcsp-wire .v{color:#00d4ff88;}
  .rcsp-wire .vb{color:#10b98188;}

  /* ── CATEGORY PANEL CONTENT ── */
  .rcsp-modes{
    display:flex;flex-wrap:wrap;gap:5px;
    padding:10px 14px;border-bottom:1px solid #0f1e2d;
  }
  .rcsp-mode-btn{
    padding:5px 10px;
    background:#060a0f;
    border:1px solid #0f1e2d;
    border-radius:2px;
    color:#2a4a60;
    font-family:'Share Tech Mono',monospace;
    font-size:9px;letter-spacing:1px;
    cursor:pointer;transition:all 0.15s;
    text-transform:uppercase;
  }
  .rcsp-mode-btn:hover{border-color:var(--cat-color,#00d4ff)44;color:#6a8a9a;}
  .rcsp-mode-btn.active{
    background:var(--cat-color,#00d4ff)0d;
    border-color:var(--cat-color,#00d4ff);
    color:var(--cat-color,#00d4ff);
  }

  /* ── ACTIONS ── */
  .rcsp-actions{
    display:flex;flex-wrap:wrap;gap:5px;
    padding:10px 14px;border-bottom:1px solid #0f1e2d;
  }
  .rcsp-action-btn{
    padding:5px 10px;
    background:#060a0f;
    border:1px solid #0f1e2d;
    border-radius:2px;
    color:#2a4a60;
    font-family:'Share Tech Mono',monospace;
    font-size:9px;letter-spacing:1px;
    cursor:pointer;transition:all 0.15s;
    text-transform:uppercase;
  }
  .rcsp-action-btn:hover{background:#0a1520;color:#6a8a9a;}
  .rcsp-action-btn:active{
    background:var(--cat-color,#00d4ff)1a;
    color:var(--cat-color,#00d4ff);
  }

  /* ── URDF SPEC BLOCK ── */
  .rcsp-spec{
    margin:10px 14px;
    background:#060a0f;
    border:1px solid #0f1e2d;
    border-radius:3px;
    padding:10px;
    font-family:'Share Tech Mono',monospace;
    font-size:8px;
    line-height:1.7;
    color:#1a3a4a;
    overflow-x:auto;
    flex:1;
  }
  .rcsp-spec .tag{color:#2a5a6a;}
  .rcsp-spec .attr{color:#1a4a5a;}
  .rcsp-spec .val{color:#00d4ff66;}
  .rcsp-spec .comment{color:#0f2a35;}

  /* ── CATEGORY-SPECIFIC EXTRA CONTROLS ── */
  .rcsp-extra{
    padding:10px 14px;
    border-bottom:1px solid #0f1e2d;
    display:flex;flex-direction:column;gap:8px;
  }
  .rcsp-extra-lbl{
    font-family:'Share Tech Mono',monospace;font-size:8px;
    color:#1a3a4a;letter-spacing:1px;text-transform:uppercase;
    margin-bottom:2px;
  }
  .rcsp-extra-row{display:flex;align-items:center;gap:8px;}
  .rcsp-extra-slider{
    -webkit-appearance:none;flex:1;height:2px;
    background:#0f1e2d;border-radius:1px;outline:none;cursor:pointer;
  }
  .rcsp-extra-slider::-webkit-slider-thumb{
    -webkit-appearance:none;width:10px;height:10px;
    border-radius:50%;background:var(--cat-color,#00d4ff);cursor:pointer;
  }
  .rcsp-extra-val{
    font-family:'Share Tech Mono',monospace;font-size:9px;
    color:var(--cat-color,#00d4ff);min-width:36px;text-align:right;
  }

  /* ── TRANSPORT ROW ── */
  .rcsp-transport{
    margin:0 14px 10px;
    display:flex;gap:6px;flex-wrap:wrap;
  }
  .rcsp-transport-badge{
    padding:3px 8px;
    background:#060a0f;border:1px solid #0f1e2d;border-radius:2px;
    font-family:'Share Tech Mono',monospace;font-size:8px;
    color:#1a3a4a;letter-spacing:1px;
  }
  .rcsp-transport-badge.active{
    border-color:var(--cat-color,#00d4ff)55;
    color:var(--cat-color,#00d4ff)88;
  }

  /* ── FOOTER ── */
  .rcsp-footer{
    width:100%;max-width:1200px;
    display:flex;justify-content:space-between;align-items:center;
    font-family:'Share Tech Mono',monospace;font-size:9px;color:#0f2a35;
    padding-top:8px;border-top:1px solid #0f1e2d;
  }
  .rcsp-footer a{color:#1a4a5a;text-decoration:none;}

  @media(max-width:700px){
    .rcsp-panel{grid-template-columns:1fr;}
    .rcsp-cats{gap:4px;}
    .rcsp-cat-btn{padding:4px 8px;font-size:10px;}
  }
`;

// ─── Joystick Component ───────────────────────────────────────────────────────
function Joystick({ label, color, onChange }) {
  const outerRef = useRef(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const dragging = useRef(false);

  const clamp = (clientX, clientY) => {
    const rect = outerRef.current.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const r = rect.width / 2 - 14;
    let dx = clientX - cx, dy = clientY - cy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist > r) { dx = dx / dist * r; dy = dy / dist * r; }
    return { x: dx, y: dy, r };
  };

  const onDown = useCallback(e => { dragging.current = true; e.preventDefault(); }, []);

  const onMove = useCallback(e => {
    if (!dragging.current) return;
    const t = e.touches?.[0] || e;
    const { x, y, r } = clamp(t.clientX, t.clientY);
    setPos({ x, y });
    onChange?.({ x: +(x / r).toFixed(2), y: +(-(y / r)).toFixed(2) });
    e.preventDefault();
  }, [onChange]);

  const onUp = useCallback(() => {
    dragging.current = false;
    setPos({ x: 0, y: 0 });
    onChange?.({ x: 0, y: 0 });
  }, [onChange]);

  useEffect(() => {
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onUp);
    };
  }, [onMove, onUp]);

  const r = 42 - 14;
  const xv = +(pos.x / r).toFixed(2);
  const yv = +(-(pos.y / r)).toFixed(2);

  return (
    <div className="stick-wrap">
      <div className="stick-lbl">{label}</div>
      <div className="stick-outer" ref={outerRef} onMouseDown={onDown} onTouchStart={onDown}>
        <div className="stick-knob" style={{
          left: `${50 + (pos.x / r) * 50}%`,
          top:  `${50 + (pos.y / r) * 50}%`,
          borderColor: color,
          boxShadow: `0 0 10px ${color}44`
        }} />
      </div>
      <div className="stick-vals">
        X:<span>{xv >= 0 ? "+" : ""}{xv}</span> Y:<span>{yv >= 0 ? "+" : ""}{yv}</span>
      </div>
    </div>
  );
}

// ─── Telemetry mock values ────────────────────────────────────────────────────
const TELEM_DEFAULTS = {
  battery: { val: 82, unit: "%", warn: v => v < 20 ? "bad" : v < 40 ? "warn" : "good" },
  temp:    { val: 41, unit: "°C", warn: v => v > 70 ? "bad" : v > 55 ? "warn" : "good" },
  voltage: { val: 47.2, unit: "V", warn: () => "good" },
  speed:   { val: 0.0, unit: "m/s", warn: () => "good" },
  altitude:{ val: 0.0, unit: "m", warn: () => "good" },
  depth:   { val: 0.0, unit: "m", warn: () => "good" },
  heading: { val: 247, unit: "°", warn: () => "good" },
  pressure:{ val: 1.0, unit: "bar", warn: () => "good" },
  gps:     { val: "FIX", unit: "", warn: v => v === "FIX" ? "good" : "warn" },
  rssi:    { val: -62, unit: "dBm", warn: v => v < -80 ? "warn" : "good" },
  payload: { val: 1.2, unit: "kg", warn: () => "good" },
  balance: { val: "OK", unit: "", warn: v => v === "OK" ? "good" : "warn" },
  ee_pos:  { val: "0,0,0", unit: "", warn: () => "good" },
  joint_torque: { val: 12.4, unit: "Nm", warn: () => "good" },
  wifi:    { val: "LINK", unit: "", warn: v => v === "LINK" ? "good" : "warn" },
};

// ─── URDF RCSP block generator ───────────────────────────────────────────────
function buildURDF(cat, speed) {
  const c = RCSP_CATEGORIES[cat];
  const maxVx = cat === "aerial" ? "10.0" : cat === "marine_surface" ? "5.0" : cat === "wheeled" ? "2.0" : "1.5";
  const ros2entries = Object.entries(c.ros2).map(([k, v]) =>
    `            <ros2_topic role="${k}" topic="${v}"/>`).join("\n");
  return `<rcsp version="1.0">
  <category>${cat}</category>
  <display_name>My ${c.label}</display_name>
  <vendor>YOUR_VENDOR</vendor>
  <capabilities>
    <locomotion
      axes="${c.leftStick?.axes.join(" ") ?? "none"}"
      max_vx="${maxVx}"
      max_wz="2.0"
      speed="${speed}"/>
    ${c.modes.length ? `<modes>${c.modes.map(m => m.toLowerCase()).join(" ")}</modes>` : ""}
    ${c.bodyPose ? `<body_pose pitch="true" roll="true" height="true"/>` : ""}
    ${c.hasArm ? `<arm ee_control="true" gripper="true"/>` : ""}
    ${c.hasAltitude ? `<altitude hold="true" max_m="120"/>` : ""}
    ${c.hasDepth ? `<depth hold="true" max_m="300"/>` : ""}
    <estop required="true"/>
  </capabilities>
  <telemetry>
    ${c.telem.map(t => `<field id="${t}" unit="${TELEM_DEFAULTS[t]?.unit ?? ""}"/>`).join("\n    ")}
  </telemetry>
  <transport>
${ros2entries}
    <mqtt topic_prefix="/robot/ROBOT_ID"
          broker="\${MQTT_BROKER:-mqtt://localhost:1883}"/>
    <websocket port="9090"/>
  </transport>
</rcsp>`;
}

// ─── Wire format generator ────────────────────────────────────────────────────
function buildWire(cat, ls, rs, speed, mode, estop) {
  const c = RCSP_CATEGORIES[cat];
  return {
    rcsp: "1.0",
    category: cat,
    type: "cmd",
    lx: ls.x, ly: ls.y,
    rx: rs?.x ?? 0, ry: rs?.y ?? 0,
    speed,
    mode,
    estop,
    // ROS2 Twist mapping
    twist: {
      linear:  { x: ls.x, y: ls.y, z: (rs?.y ?? 0) * (c.hasAltitude || c.hasDepth ? 1 : 0) },
      angular: { x: 0, y: 0, z: rs?.x ?? 0 }
    },
    ts: Date.now()
  };
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function RCSP1Controller() {
  const [activeCat, setActiveCat] = useState("legged");
  const [connected, setConnected] = useState(true);
  const [estop, setEstop] = useState(false);
  const [speed, setSpeed] = useState(50);
  const [activeMode, setActiveMode] = useState(0);
  const [ls, setLs] = useState({ x: 0, y: 0 });
  const [rs, setRs] = useState({ x: 0, y: 0 });
  const [time, setTime] = useState(new Date());
  const [altSlider, setAltSlider] = useState(0);
  const [depthSlider, setDepthSlider] = useState(0);
  const [armExt, setArmExt] = useState(50);

  const cat = RCSP_CATEGORIES[activeCat];
  const wire = buildWire(activeCat, ls, rs, speed / 100, cat.modes[activeMode], estop);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // reset state on category change
  useEffect(() => {
    setActiveMode(0);
    setEstop(false);
    setLs({ x: 0, y: 0 });
    setRs({ x: 0, y: 0 });
  }, [activeCat]);

  const cssColor = cat.color;

  return (
    <>
      <style>{STYLES}</style>
      <div className="rcsp-root" style={{ "--cat-color": cssColor }}>

        {/* ── HEADER ── */}
        <div className="rcsp-header">
          <div className="rcsp-wordmark">
            <div className="rcsp-title">RCSP-1</div>
            <div className="rcsp-subtitle">Robot Control Standard Profile · v1.0 · Indo-Mars / MarsGeo</div>
          </div>
          <div className="rcsp-meta">
            <span>UTC <span className="v">{time.toISOString().slice(11,19)}</span></span>
            <span>CAT <span className="v">{activeCat}</span></span>
            <span>CONN <span className="ok">{connected ? "ONLINE" : "OFFLINE"}</span></span>
            <span>ESTOP <span style={{color: estop ? "#ef4444" : "#10b981"}}>{estop ? "ACTIVE" : "CLEAR"}</span></span>
          </div>
        </div>

        {/* ── CATEGORY SELECTOR ── */}
        <div className="rcsp-selector">
          <div className="rcsp-selector-label">RCSP-1 Morphology Category — select to load profile</div>
          <div className="rcsp-cats">
            {Object.values(RCSP_CATEGORIES).map(c => (
              <button
                key={c.id}
                className={`rcsp-cat-btn ${activeCat === c.id ? "active" : ""}`}
                style={{ "--cat-color": c.color }}
                onClick={() => setActiveCat(c.id)}
              >
                <span className="rcsp-cat-icon">{c.icon}</span>
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── MAIN PANEL ── */}
        <div className="rcsp-panel" style={{ "--cat-color": cssColor }}>

          {/* LEFT — SHARED CORE */}
          <div className="rcsp-core">
            <div className="rcsp-sec-hdr">
              <div className="rcsp-sec-title">CORE CONTROL</div>
              <div className="rcsp-sec-badge">RCSP-1 §3 — MANDATORY</div>
            </div>

            {/* Connection */}
            <div className="rcsp-conn-row">
              <div className={`rcsp-conn-dot ${connected && !estop ? "" : "off"}`} />
              <div>
                <div className="rcsp-conn-name">{cat.label}</div>
                <div className="rcsp-conn-sub">{cat.description}</div>
              </div>
              <button className="rcsp-conn-toggle" onClick={() => setConnected(c => !c)}>
                {connected ? "DISC" : "CONN"}
              </button>
            </div>

            {/* Telemetry */}
            <div className="rcsp-telem">
              {cat.telem.slice(0, 5).map(t => {
                const d = TELEM_DEFAULTS[t];
                if (!d) return null;
                const cls = d.warn(d.val);
                return (
                  <div className="rcsp-tel-item" key={t}>
                    <div className={`rcsp-tel-val ${cls}`}>
                      {typeof d.val === "number" ? d.val.toFixed(d.val < 10 ? 1 : 0) : d.val}
                      {d.unit}
                    </div>
                    <div className="rcsp-tel-lbl">{t.toUpperCase()}</div>
                  </div>
                );
              })}
            </div>

            {/* E-STOP */}
            <div className="rcsp-estop-wrap">
              <button
                className={`rcsp-estop ${estop ? "active" : ""}`}
                onClick={() => setEstop(e => !e)}
              >
                {estop ? "⚠ E-STOP ACTIVE — TAP TO RESUME" : "E-STOP"}
              </button>
            </div>

            {/* Speed */}
            <div className="rcsp-speed-row">
              <span>SPEED</span>
              <input type="range" min="0" max="100" value={speed}
                className="rcsp-slider"
                onChange={e => setSpeed(+e.target.value)} />
              <span className="rcsp-speed-val">{speed}%</span>
            </div>

            {/* Joysticks */}
            <div className="rcsp-sticks">
              <Joystick
                label={cat.leftStick?.label ?? "LEFT"}
                color={cssColor}
                onChange={setLs}
              />
              {cat.rightStick ? (
                <Joystick
                  label={cat.rightStick.label}
                  color={cssColor}
                  onChange={setRs}
                />
              ) : (
                <div className="stick-placeholder">NO RIGHT<br/>STICK</div>
              )}
            </div>

            {/* Wire format live readout */}
            <div className="rcsp-wire">
              <div><span className="k">// RCSP-1 wire frame (JSON·MQTT·WS)</span></div>
              <div><span className="k">lx:</span><span className="v">{wire.lx.toFixed(2)}</span> <span className="k">ly:</span><span className="v">{wire.ly.toFixed(2)}</span> <span className="k">rx:</span><span className="v">{wire.rx.toFixed(2)}</span> <span className="k">ry:</span><span className="v">{wire.ry.toFixed(2)}</span></div>
              <div><span className="k">speed:</span><span className="v">{wire.speed.toFixed(2)}</span> <span className="k">mode:</span><span className="v">"{wire.mode}"</span> <span className="k">estop:</span><span className="vb">{String(wire.estop)}</span></div>
              <div><span className="k">twist.linear:</span> <span className="v">x={wire.twist.linear.x.toFixed(2)} y={wire.twist.linear.y.toFixed(2)} z={wire.twist.linear.z.toFixed(2)}</span></div>
              <div><span className="k">twist.angular:</span> <span className="v">z={wire.twist.angular.z.toFixed(2)}</span></div>
            </div>

            {/* Transport badges */}
            <div className="rcsp-transport">
              {Object.entries(cat.ros2).map(([k, v]) => (
                <div key={k} className="rcsp-transport-badge active">ROS2·{v}</div>
              ))}
              <div className="rcsp-transport-badge active">MQTT·/robot/{activeCat}</div>
              <div className="rcsp-transport-badge active">WS·:9090</div>
            </div>
          </div>

          {/* RIGHT — CATEGORY-SPECIFIC */}
          <div className="rcsp-catpanel">
            <div className="rcsp-sec-hdr">
              <div className="rcsp-sec-title">{cat.icon} {cat.label}</div>
              <div className="rcsp-sec-badge">RCSP-1 §4 — PROFILE</div>
            </div>

            {/* Modes */}
            <div className="rcsp-sec-hdr" style={{padding:"6px 14px",background:"transparent",borderBottom:"1px solid #0f1e2d"}}>
              <div className="rcsp-sec-title" style={{fontSize:9,color:"#1a3a4a"}}>LOCOMOTION MODES</div>
            </div>
            <div className="rcsp-modes">
              {cat.modes.map((m, i) => (
                <button key={m}
                  className={`rcsp-mode-btn ${activeMode === i ? "active" : ""}`}
                  onClick={() => { setActiveMode(i); setEstop(false); }}
                >{m}</button>
              ))}
            </div>

            {/* Actions */}
            <div className="rcsp-sec-hdr" style={{padding:"6px 14px",background:"transparent",borderBottom:"1px solid #0f1e2d"}}>
              <div className="rcsp-sec-title" style={{fontSize:9,color:"#1a3a4a"}}>ACTIONS</div>
            </div>
            <div className="rcsp-actions">
              {cat.actions.map(a => (
                <button key={a} className="rcsp-action-btn">{a}</button>
              ))}
            </div>

            {/* Category-specific extras */}
            {(cat.hasAltitude || cat.hasDepth || cat.bodyPose || cat.hasArm) && (
              <>
                <div className="rcsp-sec-hdr" style={{padding:"6px 14px",background:"transparent",borderBottom:"1px solid #0f1e2d"}}>
                  <div className="rcsp-sec-title" style={{fontSize:9,color:"#1a3a4a"}}>PROFILE CONTROLS</div>
                </div>
                <div className="rcsp-extra">
                  {cat.hasAltitude && (
                    <div>
                      <div className="rcsp-extra-lbl">TARGET ALTITUDE</div>
                      <div className="rcsp-extra-row">
                        <input type="range" min="0" max="120" value={altSlider}
                          className="rcsp-extra-slider"
                          onChange={e => setAltSlider(+e.target.value)} />
                        <span className="rcsp-extra-val">{altSlider}m</span>
                      </div>
                    </div>
                  )}
                  {cat.hasDepth && (
                    <div>
                      <div className="rcsp-extra-lbl">TARGET DEPTH</div>
                      <div className="rcsp-extra-row">
                        <input type="range" min="0" max="300" value={depthSlider}
                          className="rcsp-extra-slider"
                          onChange={e => setDepthSlider(+e.target.value)} />
                        <span className="rcsp-extra-val">{depthSlider}m</span>
                      </div>
                    </div>
                  )}
                  {cat.bodyPose && (
                    <>
                      <div>
                        <div className="rcsp-extra-lbl">BODY HEIGHT</div>
                        <div className="rcsp-extra-row">
                          <input type="range" min="-100" max="100" defaultValue="0"
                            className="rcsp-extra-slider" />
                          <span className="rcsp-extra-val">0cm</span>
                        </div>
                      </div>
                      <div>
                        <div className="rcsp-extra-lbl">BODY PITCH</div>
                        <div className="rcsp-extra-row">
                          <input type="range" min="-30" max="30" defaultValue="0"
                            className="rcsp-extra-slider" />
                          <span className="rcsp-extra-val">0°</span>
                        </div>
                      </div>
                    </>
                  )}
                  {cat.hasArm && (
                    <div>
                      <div className="rcsp-extra-lbl">ARM EXTENSION</div>
                      <div className="rcsp-extra-row">
                        <input type="range" min="0" max="100" value={armExt}
                          className="rcsp-extra-slider"
                          onChange={e => setArmExt(+e.target.value)} />
                        <span className="rcsp-extra-val">{armExt}%</span>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* URDF RCSP block */}
            <div className="rcsp-sec-hdr" style={{padding:"6px 14px",background:"transparent",borderBottom:"1px solid #0f1e2d"}}>
              <div className="rcsp-sec-title" style={{fontSize:9,color:"#1a3a4a"}}>URDF RCSP-1 COMPLIANCE BLOCK</div>
              <div className="rcsp-sec-badge">Copy → paste into your URDF</div>
            </div>
            <pre className="rcsp-spec">
              {buildURDF(activeCat, speed / 100).split("\n").map((line, i) => {
                const colored = line
                  .replace(/(<\/?[\w]+)/g, '<span class="tag">$1</span>')
                  .replace(/([\w_]+)=/g, '<span class="attr">$1</span>=')
                  .replace(/"([^"]*)"/g, '"<span class="val">$1</span>"')
                  .replace(/(<!--.*?-->)/g, '<span class="comment">$1</span>');
                return <div key={i} dangerouslySetInnerHTML={{ __html: colored }} />;
              })}
            </pre>

            {/* Examples */}
            <div style={{padding:"8px 14px 12px",fontFamily:"'Share Tech Mono',monospace",fontSize:"8px",color:"#1a3a4a",lineHeight:1.8}}>
              <div style={{color:"#1a3a4a",letterSpacing:"1px",marginBottom:4}}>RCSP-1 COMPLIANT ROBOTS IN THIS CATEGORY:</div>
              <div style={{color:"#2a5a6a"}}>{cat.examples}</div>
            </div>
          </div>
        </div>

        {/* ── FOOTER ── */}
        <div className="rcsp-footer">
          <span>RCSP-1 · Robot Control Standard Profile v1.0 · Indo-Mars / MarsGeo Platform · Apache 2.0</span>
          <span>9 categories · ROS2 Twist · MQTT · WebSocket · URDF extension</span>
        </div>
      </div>
    </>
  );
}
