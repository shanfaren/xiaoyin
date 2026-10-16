import bpy,math
from mathutils import Quaternion,Vector

def author_actions(arm):
    arm.animation_data_clear()
    for name in ('Idle','Speaking','Listening'):
        action=bpy.data.actions.get(name)
        if action:bpy.data.actions.remove(action)
    arm.animation_data_create();actions={}
    def rotate(name,rotations):
        pose=arm.pose.bones[name];pose.rotation_mode='QUATERNION';q=Quaternion()
        inverse=arm.data.bones[name].matrix_local.to_3x3().inverted()
        for axis,angle in rotations:q=q@Quaternion(inverse@Vector(axis),angle)
        pose.rotation_quaternion=q
    for clip in ('Idle','Speaking','Listening'):
        action=bpy.data.actions.new(clip);arm.animation_data.action=action;actions[clip]=action
        for frame in range(1,122,4):
            t=(frame-1)/30;phase=2*math.pi*t/4
            for pose in arm.pose.bones:pose.rotation_mode='QUATERNION';pose.rotation_quaternion=Quaternion()
            rotate('Chest',[((0,1,0),.008*math.sin(phase))])
            if clip=='Speaking':
                rotate('Head',[((1,0,0),.020*math.sin(phase*2)),((0,0,1),.022*math.sin(phase))])
                rotate('Jaw',[((1,0,0),.125*(.5+.5*math.sin(phase*12)))])
                for sign,side in ((1,'Left'),(-1,'Right')):
                    wave=.5+.5*math.sin(phase+(2.2 if sign<0 else 0))
                    rotate(side+'Arm',[((1,0,0),-.32*wave),((0,1,0),-sign*.25*wave)])
                    rotate(side+'ForeArm',[((1,0,0),-.80*wave)])
                    rotate(side+'Hand',[((0,0,1),sign*.15*wave*math.sin(phase*3))])
            elif clip=='Listening':rotate('Head',[((0,1,0),-.045)])
            for pose in arm.pose.bones:pose.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=pose.name)
        track=arm.animation_data.nla_tracks.new();track.name=clip
        strip=track.strips.new(clip,1,action);strip.action_slot=arm.animation_data.action_slot;track.mute=True
    arm.animation_data.action=actions['Idle'];bpy.context.scene.frame_set(1)
    return actions
