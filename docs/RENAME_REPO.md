# Rename Repository to career-co-pilot-pro

## 1. Push current changes (to existing job-automation repo)

```bash
git push origin main
```

## 2. Rename on GitHub

1. Go to https://github.com/Santhakumarramesh/job-automation/settings
2. Under **Repository name**, change `job-automation` to `career-co-pilot-pro`
3. Click **Rename**

GitHub will automatically redirect old URLs to the new one.

## 3. Update local git remote

After renaming on GitHub, run:

```bash
git remote set-url origin https://github.com/Santhakumarramesh/career-co-pilot-pro.git
git fetch origin
git push origin main
```

## 4. Verify

```bash
git remote -v
# Should show: origin  https://github.com/Santhakumarramesh/career-co-pilot-pro.git
```
