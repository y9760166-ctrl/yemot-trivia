import os
import requests
from datetime import datetime
from flask import Flask, request, Response

app = Flask(__name__)

# מיפוי האותיות לתפקידי התשובות וההכרזות הקוליות
ITEM_LABELS = {
    "Q": "לעריכת השאלה הקישו 0",
    "A": "לעריכת התשובה הנכונה הקישו 1",
    "B": "לעריכת התשובה השגויה הראשונה הקישו 2",
    "C": "לעריכת התשובה השגויה השנייה הקישו 3",
    "D": "לעריכת התשובה השגויה השלישית הקישו 4",
    "E": "לעריכת התשובה השגויה הרביעית הקישו 5"
}

ITEM_KEYS = {
    "0": "Q",
    "1": "A",
    "2": "B",
    "3": "C",
    "4": "D",
    "5": "E"
}

def get_today_hebrew_date_string():
    """
    חישוב תאריך עברי בפורמט 8 ספרות ברצף (YYYYMMDD):
    דוגמה: ט"ז תשרי תשפ"ז = 57870116
    """
    try:
        from pyluach import dates
        today_hebrew = dates.HebrewDate.today()
        return f"{today_hebrew.year:04d}{today_hebrew.month:02d}{today_hebrew.day:02d}"
    except Exception:
        now = datetime.now()
        hebrew_year = now.year + 3760
        if now.month >= 9:
            hebrew_year += 1
        month_map = {9: 1, 10: 2, 11: 3, 12: 4, 1: 5, 2: 6, 3: 7, 4: 8, 5: 9, 6: 10, 7: 11, 8: 12}
        hebrew_month = month_map.get(now.month, 1)
        hebrew_day = min(now.day, 30)
        return f"{hebrew_year:04d}{hebrew_month:02d}{hebrew_day:02d}"

def extract_token(params):
    """
    חילוץ אוטומטי של הטוקן מתוך הבקשה הנכנסת או משתנה הסביבה
    """
    token = os.environ.get("YEMOT_TOKEN", "083136585:456987").strip()
    if token:
        return token
    if params.get("token"):
        return str(params.get("token")).strip()
    if params.get("ApiToken"):
        return str(params.get("ApiToken")).strip()
    return ""

def extract_dtmf(params):
    """
    חילוץ נקי של המקש שהוקש בלבד מכל השדות האפשריים
    """
    if params.get("ApiDTMF") is not None and str(params.get("ApiDTMF")).strip() != "":
        return str(params.get("ApiDTMF")).strip()
    if params.get("dtmf") is not None and str(params.get("dtmf")).strip() != "":
        return str(params.get("dtmf")).strip()
    return ""

def delete_file_from_yemot(token, file_path):
    """
    מחיקת קובץ משרתי ימות המשיח
    """
    if not token:
        return
    try:
        url = f"https://www.call2all.co.il/ym/api/DeleteFile?token={requests.utils.quote(token)}&what={requests.utils.quote('ivar:/' + file_path)}"
        requests.get(url, timeout=2.0)
    except Exception:
        pass

def response_read(messages, val_name, type_val, min_val, max_val, timeout, tap, valid_digits):
    """
    בניית פקודת read תקנית ומדויקת לימות המשיח
    """
    return f"read={messages}={val_name},{type_val},{min_val},{max_val},{timeout},{tap},no,{valid_digits}"

def send_yemot_response(body_text):
    return Response(body_text, mimetype="text/plain; charset=utf-8", status=200)

def scan_today_trivia_structure(trivia_folder, token):
    """
    סריקת מבנה הטריוויה היומי
    """
    calculated_today_str = get_today_hebrew_date_string()
    
    trivia_data = {
        "date_folder": calculated_today_str,
        "date_folder_path": f"{trivia_folder}/{calculated_today_str}",
        "questions": []
    }

    if not token:
        trivia_data["questions"] = [
            {
                "display_idx": 1,
                "q_folder_name": "000",
                "q_full_path": f"{trivia_folder}/{calculated_today_str}/000",
                "files": {
                    "Q": f"{trivia_folder}/{calculated_today_str}/000/Q.wav",
                    "A": f"{trivia_folder}/{calculated_today_str}/000/A.wav"
                }
            }
        ]
        return trivia_data

    try:
        clean_path = str(trivia_folder).strip('/')
        url_root = f"https://www.call2all.co.il/ym/api/GetIVR2Dir?token={requests.utils.quote(token)}&path={requests.utils.quote('ivar:/' + clean_path)}"
        res_root = requests.get(url_root, timeout=2.5).json()

        date_folder_to_use = ""
        if res_root.get("responseStatus") == "OK":
            dirs = res_root.get("dirs", []) or res_root.get("folders", [])
            existing_date_folders = []
            
            for d in dirs:
                d_name = d.get("name", "") if isinstance(d, dict) else str(d)
                if d_name.isdigit() and len(d_name) == 8:
                    existing_date_folders.append(d_name)

            if calculated_today_str in existing_date_folders:
                date_folder_to_use = calculated_today_str
            elif existing_date_folders:
                existing_date_folders.sort()
                date_folder_to_use = existing_date_folders[-1]

        if not date_folder_to_use:
            date_folder_to_use = calculated_today_str

        date_folder_path = f"{clean_path}/{date_folder_to_use}"
        trivia_data["date_folder"] = date_folder_to_use
        trivia_data["date_folder_path"] = date_folder_path

        url_date = f"https://www.call2all.co.il/ym/api/GetIVR2Dir?token={requests.utils.quote(token)}&path={requests.utils.quote('ivar:/' + date_folder_path)}"
        res_date = requests.get(url_date, timeout=2.5).json()

        question_folders = []
        if res_date.get("responseStatus") == "OK":
            q_dirs = res_date.get("dirs", []) or res_date.get("folders", [])
            for qd in q_dirs:
                q_name = qd.get("name", "") if isinstance(qd, dict) else str(qd)
                if q_name.isdigit():
                    question_folders.append(q_name)

        question_folders.sort()

        for idx, q_folder_name in enumerate(question_folders, start=1):
            q_full_path = f"{date_folder_path}/{q_folder_name}"
            url_q = f"https://www.call2all.co.il/ym/api/GetIVR2Dir?token={requests.utils.quote(token)}&path={requests.utils.quote('ivar:/' + q_full_path)}"
            res_q = requests.get(url_q, timeout=2.0).json()

            existing_files = {}
            if res_q.get("responseStatus") == "OK":
                files = res_q.get("files", [])
                for f in files:
                    f_name = f.get("name", "")
                    if f_name.lower().endswith(".wav"):
                        letter = f_name[:-4].upper()
                        existing_files[letter] = f"{q_full_path}/{f_name}"

            if not existing_files:
                existing_files = {
                    "Q": f"{q_full_path}/Q.wav",
                    "A": f"{q_full_path}/A.wav"
                }

            trivia_data["questions"].append({
                "display_idx": idx,
                "q_folder_name": q_folder_name,
                "q_full_path": q_full_path,
                "files": existing_files
            })

    except Exception as e:
        print(f"Error scanning trivia date structure: {e}")

    if not trivia_data["questions"]:
        default_q_path = f"{trivia_folder}/{calculated_today_str}/000"
        trivia_data["questions"].append({
            "display_idx": 1,
            "q_folder_name": "000",
            "q_full_path": default_q_path,
            "files": {
                "Q": f"{default_q_path}/Q.wav",
                "A": f"{default_q_path}/A.wav"
            }
        })

    return trivia_data

def handle_select_question(dtmf, trivia_data, trivia_folder):
    questions = trivia_data.get("questions", [])
    total_questions = len(questions)

    if total_questions == 0:
        return "id_list_message=t-לא נמצאו הקלטות טריוויה עבור היום. להתראות.&hangup=yes"

    if dtmf == '*':
        return "id_list_message=t-תודה ושלום.&hangup=yes"

    prompt_list = [
        "t-נמצאו",
        f"n-{total_questions}",
        "t-שאלות להיום אנא בחרו את מספר השאלה לניהול"
    ]

    valid_digits_list = ["*"]
    for i in range(1, total_questions + 1):
        prompt_list.append("t-לשאלה")
        prompt_list.append(f"n-{i}")
        prompt_list.append("t-הקישו")
        prompt_list.append(f"n-{i}")
        valid_digits_list.append(str(i))

    prompt_str = ".".join(prompt_list)
    valid_digits_str = ",".join(valid_digits_list)

    return response_read(prompt_str, "dtmf", "digits", 1, 1, 7, "b", valid_digits_str) + \
           f"&step=select_question&trivia_folder={trivia_folder}"

def build_select_item_prompt(q_idx, trivia_data, trivia_folder):
    """
    בניית תפריט עריכת הקבצים בשאלה (שלב 2)
    """
    questions = trivia_data.get("questions", [])
    
    target_question = None
    if 0 < q_idx <= len(questions):
        target_question = questions[q_idx - 1]
    
    date_folder = trivia_data.get("date_folder", get_today_hebrew_date_string())
    q_folder_name = f"{(q_idx - 1):03d}" if q_idx > 0 else "000"
    q_full_path = f"{trivia_folder}/{date_folder}/{q_folder_name}"

    if target_question and target_question.get("files"):
        existing_files = target_question.get("files")
    else:
        existing_files = {
            "Q": f"{q_full_path}/Q.wav",
            "A": f"{q_full_path}/A.wav",
            "B": f"{q_full_path}/B.wav"
        }

    prompt_list = [
        "t-שאלה מספר",
        f"n-{q_idx}"
    ]

    valid_digits_list = ["*"]

    # הקראת האפשרויות הזמינות
    for digit, letter in ITEM_KEYS.items():
        if letter in existing_files:
            prompt_list.append(f"t-{ITEM_LABELS[letter]}")
            valid_digits_list.append(digit)

    if len(valid_digits_list) == 1:
        prompt_list.append("t-לעריכת השאלה הקישו 0. לעריכת התשובה הנכונה הקישו 1")
        valid_digits_list.extend(["0", "1"])

    prompt_str = ".".join(prompt_list)
    valid_digits_str = ",".join(valid_digits_list)

    return response_read(prompt_str, "dtmf", "digits", 1, 1, 7, "b", valid_digits_str) + \
           f"&step=select_item&q_idx={q_idx}&trivia_folder={trivia_folder}"

def handle_select_item(dtmf, q_idx, trivia_data, trivia_folder):
    """
    טיפול בבחירת רכיב לעריכה (שלב 2) - מעבר ישיר מובטח ל-action_menu!
    """
    if dtmf == '*':
        return handle_select_question('', trivia_data, trivia_folder)

    if q_idx <= 0:
        q_idx = 1

    date_folder = trivia_data.get("date_folder", get_today_hebrew_date_string())
    q_folder_name = f"{(q_idx - 1):03d}"
    
    questions = trivia_data.get("questions", [])
    target_question = questions[q_idx - 1] if 0 < q_idx <= len(questions) else None

    # אם המשתמש מקיש מקש תואם רכיב (0=Q, 1=A, 2=B...)
    if dtmf in ITEM_KEYS:
        letter = ITEM_KEYS[dtmf]
        file_path = ""
        
        if target_question and target_question.get("files") and letter in target_question["files"]:
            file_path = target_question["files"][letter]
        else:
            file_path = f"{trivia_folder}/{date_folder}/{q_folder_name}/{letter}.wav"
            
        return build_action_menu_prompt(q_idx, letter, file_path, trivia_folder)

    return build_select_item_prompt(q_idx, trivia_data, trivia_folder)

def build_action_menu_prompt(q_idx, letter, file_path, trivia_folder):
    """
    בניית תפריט M1009 לעריכת הקובץ
    """
    return response_read("m-1009", "dtmf", "digits", 1, 1, 7, "b", "1,2,3,4,*") + \
           f"&step=action_menu&q_idx={q_idx}&letter={letter}&file_path={requests.utils.quote(file_path)}&trivia_folder={trivia_folder}"

def handle_action_menu(dtmf, q_idx, letter, file_path, trivia_data, trivia_folder, token):
    if dtmf == '*':
        return build_select_item_prompt(q_idx, trivia_data, trivia_folder)

    if dtmf == '1':
        # 1 - שמיעת ההקלטה
        play_prompt = f"f-{file_path}.m-1009"
        return response_read(play_prompt, "dtmf", "digits", 1, 1, 7, "b", "1,2,3,4,*") + \
               f"&step=action_menu&q_idx={q_idx}&letter={letter}&file_path={requests.utils.quote(file_path)}&trivia_folder={trivia_folder}"

    elif dtmf == '2':
        # 2 - אישור ההקלטה
        return build_post_edit_prompt(q_idx, trivia_folder)

    elif dtmf == '3':
        # 3 - הקלטה מחודשת ושמירה במיקום המדויק
        return response_read("t-אנא הקליטו את ההודעה לאחר הצליל בסיום הקישו סולמית", "rec_file", "voice", 1, 10, 60, "b", "#") + \
               f"&save_file_path={file_path}&step=post_edit_menu&q_idx={q_idx}&trivia_folder={trivia_folder}"

    elif dtmf == '4':
        # 4 - מחיקת הקובץ
        delete_file_from_yemot(token, file_path)
        return response_read("t-ההקלטה נמחקה בהצלחה." + get_post_edit_prompt_text(), "dtmf", "digits", 1, 1, 7, "b", "1,2,3,*") + \
               f"&step=post_edit_menu&q_idx={q_idx}&trivia_folder={trivia_folder}"

    else:
        return build_action_menu_prompt(q_idx, letter, file_path, trivia_folder)

def get_post_edit_prompt_text():
    return "t-לעריכה נוספת בשאלה זו הקישו 1 לבחירת שאלה אחרת לניהול הקישו 2 ליציאה הקישו 3"

def build_post_edit_prompt(q_idx, trivia_folder):
    return response_read(get_post_edit_prompt_text(), "dtmf", "digits", 1, 1, 7, "b", "1,2,3,*") + \
           f"&step=post_edit_menu&q_idx={q_idx}&trivia_folder={trivia_folder}"

def handle_post_edit_menu(dtmf, q_idx, trivia_data, trivia_folder):
    if dtmf == '1':
        return build_select_item_prompt(q_idx, trivia_data, trivia_folder)
    elif dtmf == '2':
        return handle_select_question('', trivia_data, trivia_folder)
    elif dtmf == '3' or dtmf == '*':
        return "id_list_message=t-תודה רבה היציאה בוצעה בהצלחה.&hangup=yes"

    return build_post_edit_prompt(q_idx, trivia_folder)

@app.route('/api/trivia', methods=['GET', 'POST'])
def trivia_endpoint():
    try:
        params = {}
        if request.args:
            params.update(request.args.to_dict())
        if request.is_json and request.json:
            params.update(request.json)
        elif request.form:
            params.update(request.form.to_dict())

        step = params.get('step', 'init')
        
        try:
            q_idx = int(params.get('q_idx', 0))
        except (ValueError, TypeError):
            q_idx = 0

        letter = params.get('letter', '')
        file_path = params.get('file_path', '')
        trivia_folder = params.get('trivia_folder', '1')

        token = extract_token(params)
        dtmf = extract_dtmf(params)

        # סריקת מבנה הטריוויה היומי
        trivia_data = scan_today_trivia_structure(trivia_folder, token)

        response_text = ""

        # ניהול ניתוב השלבים - חסין תקלות ואינו קופץ חזרה!
        if step in ['init', 'select_question']:
            if dtmf != '' and dtmf != '*':
                try:
                    selected_idx = int(dtmf)
                    response_text = build_select_item_prompt(selected_idx, trivia_data, trivia_folder)
                except ValueError:
                    response_text = handle_select_question(dtmf, trivia_data, trivia_folder)
            else:
                response_text = handle_select_question(dtmf, trivia_data, trivia_folder)

        elif step == 'select_item':
            # מעבר ישיר אם הוקש מקש תואם
            if dtmf in ITEM_KEYS:
                letter = ITEM_KEYS[dtmf]
                date_folder = trivia_data.get("date_folder", get_today_hebrew_date_string())
                q_folder_name = f"{(q_idx - 1):03d}" if q_idx > 0 else "000"
                
                # חיפוש נתיב מועדף
                target_q = trivia_data["questions"][q_idx - 1] if 0 < q_idx <= len(trivia_data.get("questions", [])) else None
                if target_q and letter in target_q.get("files", {}):
                    target_file_path = target_q["files"][letter]
                else:
                    target_file_path = f"{trivia_folder}/{date_folder}/{q_folder_name}/{letter}.wav"
                    
                response_text = build_action_menu_prompt(q_idx, letter, target_file_path, trivia_folder)
            else:
                response_text = handle_select_item(dtmf, q_idx, trivia_data, trivia_folder)

        elif step == 'action_menu':
            response_text = handle_action_menu(dtmf, q_idx, letter, file_path, trivia_data, trivia_folder, token)

        elif step == 'post_edit_menu':
            response_text = handle_post_edit_menu(dtmf, q_idx, trivia_data, trivia_folder)

        else:
            response_text = handle_select_question('', trivia_data, trivia_folder)

        return send_yemot_response(response_text)

    except Exception as error:
        print(f"Error in Trivia API Endpoint: {error}")
        return send_yemot_response("id_list_message=t-אירעה שגיאה במערכת הניהול.&hangup=yes")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
