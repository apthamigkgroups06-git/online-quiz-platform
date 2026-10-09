INSERT INTO quizzes (id,title,limit_seconds,negative_marks,partial_credit)
VALUES (1,'Git Basics',300,0.25,TRUE) ON CONFLICT DO NOTHING;
SELECT setval('quizzes_id_seq', GREATEST((SELECT MAX(id) FROM quizzes),1));

INSERT INTO questions (quiz_id,prompt,choices,correct,marks) VALUES
 (1,'Which command stages a file?','["git add","git commit","git push","git log"]','{0}',1),
 (1,'What does a commit store?','["a diff","a full snapshot","a branch","a remote"]','{1}',1),
 (1,'Which are local-only commands?','["merge","push","commit","pull"]','{0,2}',2)
ON CONFLICT DO NOTHING;
