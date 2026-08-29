from .resume_analyzer import analyze_resume


TEST_RESUME = """
John Doe

Backend Developer

Experienced software developer specializing in
Python backend development.

Skills:
Python, FastAPI, PostgreSQL, Docker, Git, REST APIs.

Experience:
Backend Developer at Example Technologies.
Developed REST APIs using Python and FastAPI.

Education:
BSc Computer Science.
"""


def main():
    profile = analyze_resume(TEST_RESUME)

    print("\nSUMMARY")
    print(profile.summary)

    print("\nSKILLS")
    for skill in profile.skills:
        print("-", skill)

    print("\nJOB TITLES")
    for title in profile.job_titles:
        print("-", title)

    print("\nEXPERIENCE")

    for experience in profile.experience:
        print(
            f"- {experience.job_title} "
            f"at {experience.company}"
        )

    print("\nEDUCATION")

    for education in profile.education:
        print(
            f"- {education.qualification} "
            f"({education.institution})"
        )


if __name__ == "__main__":
    main()