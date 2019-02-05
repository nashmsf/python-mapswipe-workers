from mapswipe_workers.basic import BaseFunctions

import random
import time


def create_build_area_result_in_firebase(project_id, task_id, user_id, firebase):
    fb_db = firebase.database()

    result_data = {
        "device": "test_device",
        "id": task_id,
        "projectId": project_id,
        "item": "test_item",
        "result": random.randint(0, 3),
        "timestamp": int(time.time()*1000),
        "user": user_id,
        "wkt": ""
    }

    fb_db.child("results").child(task_id).child(user_id).child("data").set(result_data)


def create_footprint_result_in_firebase(project_id, task_id, user_id, firebase):
    fb_db = firebase.database()

    result_data = {
        "device": "test_device",
        "id": task_id,
        "projectId": project_id,
        "item": "test_item",
        "result": random.randint(1, 3),
        "timestamp": int(time.time()*1000),
        "user": user_id,
        "wkt": ""
    }

    fb_db.child("results").child(task_id).child(user_id).child("data").set(result_data)


def simulate_user_contributions(project_id, project_type, user_id='test_user', modus='development'):
    firebase, postgres = BaseFunctions.get_environment(modus)

    # get groups from firebase for this project
    fb_db = firebase.database()
    groups = fb_db.child("groups").child(project_id).order_by_child("completedCount").limit_to_first(5).get()

    for group in groups.each():
        group_id = group.key()
        val = group.val()

        tasks = val['tasks']
        task_ids = tasks.keys()

        if project_type == 1:
            count = val['count']
            random_sample = random.sample(task_ids, int(count/2))
            for task_id in random_sample:
                create_build_area_result_in_firebase(project_id, task_id, user_id, firebase, modus)
            print("created build area results in firebase")
        elif project_type == 2:
            for task_id in task_ids:
                create_footprint_result_in_firebase(project_id, task_id, user_id, firebase, modus)
            print("created footprint results in firebase")

        # update groups completed count
        old_completed_count = fb_db.child("groups").child(project_id).child(group_id).child("completedCount").get().val()
        fb_db.child("groups").child(project_id).child(group_id).update({"completedCount":old_completed_count+1})
        print("updated completed count")


modus = 'production'

project_id = 13555
project_type = 1
simulate_user_contributions(project_id, project_type, modus)

project_id = 13541
project_type = 2
simulate_user_contributions(project_id, project_type, modus)

# run transfer results from firebase to postgres
BaseFunctions.run_transfer_results(modus)
