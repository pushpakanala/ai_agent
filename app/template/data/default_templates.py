DEFAULT_TEMPLATES = [

    # ==================================================
    # WORK
    # ==================================================
    {
        "id": "leave_request",
        "name": "Leave Request",
        "category": "Work",
        "prompt_template":
            "Write a professional leave request to {manager} because of {reason}."
    },

    {
        "id": "sick_leave",
        "name": "Sick Leave",
        "category": "Work",
        "prompt_template":
            "Write a sick leave email to {manager}. Mention that I am unwell and need leave for {days} day(s)."
    },

    {
        "id": "work_from_home",
        "name": "Work From Home Request",
        "category": "Work",
        "prompt_template":
            "Write a professional work-from-home request to {manager} because of {reason}."
    },

    {
        "id": "meeting_request",
        "name": "Meeting Request",
        "category": "Work",
        "prompt_template":
            "Write an email requesting a meeting with {person} regarding {topic}."
    },

    {
        "id": "meeting_follow_up",
        "name": "Meeting Follow-up",
        "category": "Work",
        "prompt_template":
            "Write a follow-up email to {person} summarizing our discussion about {topic}."
    },

    {
        "id": "weekly_status_update",
        "name": "Weekly Status Update",
        "category": "Work",
        "prompt_template":
            "Write a weekly status update email to {manager} highlighting achievements, blockers, and next steps."
    },

    # ==================================================
    # CAREER
    # ==================================================
    {
        "id": "interview_thank_you",
        "name": "Interview Thank You",
        "category": "Career",
        "prompt_template":
            "Write a thank-you email to {company} after interviewing for the role of {role}."
    },

    {
        "id": "job_follow_up",
        "name": "Job Application Follow-up",
        "category": "Career",
        "prompt_template":
            "Write a professional follow-up email to {company} regarding my application for {role}."
    },

    {
        "id": "referral_request",
        "name": "Referral Request",
        "category": "Career",
        "prompt_template":
            "Write a polite referral request to {person} for the role {role} at {company}."
    },

    {
        "id": "offer_acceptance",
        "name": "Offer Acceptance",
        "category": "Career",
        "prompt_template":
            "Write an offer acceptance email to {company} for the position of {role}."
    },

    {
        "id": "resignation_letter",
        "name": "Resignation Letter",
        "category": "Career",
        "prompt_template":
            "Write a professional resignation email to {manager} with a notice period of {notice_period}."
    },

    # ==================================================
    # BUSINESS
    # ==================================================
    {
        "id": "client_follow_up",
        "name": "Client Follow-up",
        "category": "Business",
        "prompt_template":
            "Write a professional follow-up email to {client} regarding {topic}."
    },

    {
        "id": "partnership_proposal",
        "name": "Partnership Proposal",
        "category": "Business",
        "prompt_template":
            "Write a partnership proposal email to {company} regarding collaboration on {topic}."
    },

    {
        "id": "invoice_reminder",
        "name": "Invoice Reminder",
        "category": "Business",
        "prompt_template":
            "Write a polite invoice reminder email to {client} regarding invoice {invoice_number}."
    },

    {
        "id": "customer_support_reply",
        "name": "Customer Support Reply",
        "category": "Business",
        "prompt_template":
            "Write a professional customer support response to {customer_name} regarding {issue}."
    },

    # ==================================================
    # ACADEMIC
    # ==================================================
    {
        "id": "recommendation_request",
        "name": "Recommendation Letter Request",
        "category": "Academic",
        "prompt_template":
            "Write an email to Professor {professor} requesting a recommendation letter for {program}."
    },

    {
        "id": "assignment_extension",
        "name": "Assignment Extension Request",
        "category": "Academic",
        "prompt_template":
            "Write an email to Professor {professor} requesting an extension for {assignment} because of {reason}."
    },

    # ==================================================
    # PERSONAL
    # ==================================================
    {
        "id": "birthday_wishes",
        "name": "Birthday Wishes",
        "category": "Personal",
        "prompt_template":
            "Write a warm birthday email to {person}."
    },

    {
        "id": "congratulations",
        "name": "Congratulations",
        "category": "Personal",
        "prompt_template":
            "Write a congratulatory email to {person} for {achievement}."
    },

    {
        "id": "apology_email",
        "name": "Apology Email",
        "category": "Personal",
        "prompt_template":
            "Write a sincere apology email to {person} regarding {reason}."
    },

    {
        "id": "invitation_email",
        "name": "Invitation Email",
        "category": "Personal",
        "prompt_template":
            "Write an invitation email to {person} for {event} on {date}."
    },

]