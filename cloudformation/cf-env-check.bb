#!/usr/bin/env bb
(ns cf-env-check
  (:require
    [babashka.fs :as fs]
    [babashka.process :as p]
    [clojure.string :as str]))

;; --------------------------------------------
;; Config
;; --------------------------------------------

(def default-allowlist
  [#"dkr\.ecr\.[^/]+/lif/dev/"     ; shared ECR repo path example
   #"arn:aws:[^:]+:[^:]*:[^:]*:"  ; generic ARN noise
   ])

(def image-ref-regex
  #"(?:\b|\")([0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\/[A-Za-z0-9._\-\/]+):([A-Za-z0-9._\-]+)(?:\b|\")")

(def suspicious-nonenv-patterns
  "If a NON-ENV diff contains these patterns, we warn (likely a mistake).
   Otherwise we just print it as INFO so you can review quickly without rabbit holes."
  [#"\.lif\.unicon\.net"               ; hostnames
   #"\.demo\." #"\.dev\."              ; env subdomains (if they show up post-normalization, suspicious)
   #"s3://[^ ]*/(dev|demo)[^ ]*"       ; env buckets/paths that somehow survived normalization
   #"/(dev|demo)/"                     ; env path that survived normalization
   #"arn:aws:iam::.*:oidc-provider/"   ; IAM/OIDC config differences are often important
   #"AssumeRole" #"Principal"          ; IAM-ish strings (common in params/templates too)
   ])

;; --------------------------------------------
;; Args
;; --------------------------------------------

(defn usage []
  (str/join
    "\n"
    ["Usage:"
     "  bb cf-env-check.bb [--dir PATH] [--no-diff] [--allow REGEX ...]"
     ""
     "--no-diff:"
     "  Do not print full diffs. Still prints whether diffs are env-only vs non-env, plus counts/warnings."
     ""
     "Exit codes:"
     "  0 = no warnings"
     "  2 = warnings found"]))

(defn parse-args [args]
  (loop [m {:dir "."
            :show-diff true
            :allow default-allowlist}
         xs args]
    (if (empty? xs)
      m
      (let [[a & more] xs]
        (cond
          (= a "--dir")
          (recur (assoc m :dir (or (first more) ".")) (rest more))

          (= a "--no-diff")
          (recur (assoc m :show-diff false) more)

          (= a "--allow")
          (let [pat (first more)]
            (when (nil? pat)
              (println "Missing value for --allow")
              (println (usage))
              (System/exit 1))
            (recur (update m :allow conj (re-pattern pat)) (rest more)))

          (or (= a "-h") (= a "--help"))
          (do (println (usage)) (System/exit 0))

          :else
          (do
            (println "Unknown arg:" a)
            (println (usage))
            (System/exit 1)))))))

;; --------------------------------------------
;; File pairing
;; --------------------------------------------

(defn starts-with? [s prefix] (str/starts-with? s prefix))

(defn file-suffix [path prefix]
  (subs (fs/file-name path) (count prefix)))

(defn list-env-files [dir]
  (->> (fs/list-dir dir)
       (filter fs/regular-file?)
       (map str)
       (filter #(or (starts-with? (fs/file-name %) "dev-")
                    (starts-with? (fs/file-name %) "demo-")))))

(defn pair-files [paths]
  (let [dev (->> paths
                 (filter #(starts-with? (fs/file-name %) "dev-"))
                 (map (fn [p] [(file-suffix p "dev-") p]))
                 (into {}))
        demo (->> paths
                  (filter #(starts-with? (fs/file-name %) "demo-"))
                  (map (fn [p] [(file-suffix p "demo-") p]))
                  (into {}))
        keys-all (sort (distinct (concat (keys dev) (keys demo))))]
    (map (fn [k] {:key k :dev (get dev k) :demo (get demo k)}) keys-all)))

;; --------------------------------------------
;; Diff + normalization helpers
;; --------------------------------------------

(defn canonicalize-env
  "Normalize common dev/demo markers into __ENV__ so only unexpected diffs remain.
   Also normalize ECR image TAGS (but not the repo/path) so expected latest-vs-pinned
   differences do not trigger non-env diffs. Docker policy is enforced separately."
  [s]
  (-> s
      ;; dev/demo tokens
      (str/replace #"\bdev\b" "__ENV__")
      (str/replace #"\bdemo\b" "__ENV__")

      (str/replace #"/dev/" "/__ENV__/")
      (str/replace #"/demo/" "/__ENV__/")

      (str/replace #"\.dev\." ".__ENV__.")
      (str/replace #"\.demo\." ".__ENV__.")

      (str/replace #"\bdev-" "__ENV__-")
      (str/replace #"\bdemo-" "__ENV__-")

      ;; normalize ECR tags only (keep repo/path intact)
      ;; example:
      ;; 3814...amazonaws.com/lif/dev/lif_advisor_api:latest
      ;; 3814...amazonaws.com/lif/dev/lif_advisor_api:2025-...
      ;; becomes:
      ;; 3814...amazonaws.com/lif/dev/lif_advisor_api:__TAG__
      (str/replace
        #"([0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\/[A-Za-z0-9._\-\/]+):([A-Za-z0-9._\-]+)"
        "$1:__TAG__")))

(defn run-diff-u [a b]
  (let [{:keys [out err exit]} (p/sh {:out :string :err :string} "diff" "-u" a b)]
    {:exit exit :text (str out err)}))

(defn diff-stats
  "Very small summary from unified diff output."
  [diff-text]
  (let [lines (str/split-lines diff-text)
        adds (count (filter #(and (str/starts-with? % "+")
                                 (not (str/starts-with? % "+++")))
                            lines))
        dels (count (filter #(and (str/starts-with? % "-")
                                 (not (str/starts-with? % "---")))
                            lines))
        hunks (count (filter #(str/starts-with? % "@@") lines))]
    {:hunks hunks :adds adds :dels dels}))

(defn write-temp [dir base-name content]
  (let [p (fs/path dir base-name)]
    (spit (str p) content)
    (str p)))

(defn normalized-diff
  "Return {:kind :none|:env-only|:non-env, :full ..., :norm ...}"
  [demo-path dev-path demo-content dev-content]
  (let [full (run-diff-u demo-path dev-path)]
    (cond
      (= 0 (:exit full))
      {:kind :none :full full}

      (= 1 (:exit full))
      (let [tmpdir (fs/create-temp-dir {:prefix "cf-env-check-"})
            demo-n (write-temp tmpdir (str (fs/file-name demo-path) ".norm") (canonicalize-env demo-content))
            dev-n  (write-temp tmpdir (str (fs/file-name dev-path)  ".norm") (canonicalize-env dev-content))
            norm (run-diff-u demo-n dev-n)]
        (fs/delete-tree tmpdir)
        (cond
          (= 0 (:exit norm)) {:kind :env-only :full full :norm norm}
          (= 1 (:exit norm)) {:kind :non-env  :full full :norm norm}
          :else              {:kind :error    :full full :norm norm}))

      :else
      {:kind :error :full full})))

(defn diff-change-lines [diff-text]
  (->> (str/split-lines diff-text)
       (filter (fn [l]
                 (and (or (str/starts-with? l "+") (str/starts-with? l "-"))
                      (not (str/starts-with? l "+++"))
                      (not (str/starts-with? l "---")))))
       (vec)))

(defn suspicious-nonenv-diff? [norm-diff-text]
  (let [changed (diff-change-lines norm-diff-text)]
    (boolean
      (some (fn [line]
              (some #(re-find % line) suspicious-nonenv-patterns))
            changed))))

;; --------------------------------------------
;; Warnings: cross-env leftovers + docker policy
;; --------------------------------------------

(defn any-allowlisted? [s allowlist]
  (some #(re-find % s) allowlist))

(defn read-lines [path] (-> (slurp path) str/split-lines))

(defn find-cross-env-leftovers
  [lines forbidden-token allowlist]
  (->> (map-indexed (fn [i line] {:line (inc i) :text line}) lines)
       (filter (fn [{:keys [text]}]
                 (and (re-find (re-pattern (str "\\b" (java.util.regex.Pattern/quote forbidden-token) "\\b")) text)
                      (not (any-allowlisted? text allowlist)))))
       (seq)))

(defn extract-image-refs [content]
  (->> (re-seq image-ref-regex content)
       (map (fn [[_ image tag]] {:image image :tag tag}))
       (seq)))

(defn check-image-policy [env filename content]
  (let [refs (extract-image-refs content)]
    (when refs
      (->> refs
           (keep (fn [{:keys [image tag]}]
                   (cond
                     (and (= env :dev) (not= tag "latest"))
                     (str filename ": dev should use :latest but found :" tag " (" image ":" tag ")")

                     (and (= env :demo) (= tag "latest"))
                     (str filename ": demo must NOT use :latest but found :" tag " (" image ":" tag ")")

                     :else nil)))
           (seq)))))

;; --------------------------------------------
;; Output
;; --------------------------------------------

(defn print-section [title]
  (println "\n============================================================")
  (println title)
  (println "============================================================"))

(defn print-compact-cross [title xs]
  (println title)
  (doseq [{:keys [line text]} (take 8 xs)]
    (println (format "  %4d | %s" line text)))
  (when (> (count xs) 8)
    (println (format "  ... (%d more)" (- (count xs) 8)))))

;; --------------------------------------------
;; Main
;; --------------------------------------------

(let [{:keys [dir show-diff allow]} (parse-args *command-line-args*)
      paths (list-env-files dir)
      pairs (pair-files paths)
      warnings (atom [])]
  (when (empty? paths)
    (println "No dev-* or demo-* files found in:" dir)
    (System/exit 0))

  (print-section (str "CloudFormation env-pair check (" dir ")"))

  (let [orphans (->> pairs (filter #(or (nil? (:dev %)) (nil? (:demo %)))) seq)]
    (when orphans
      (swap! warnings conj "Orphans found (missing counterpart)")
      (println "\nOrphans (missing counterpart):")
      (doseq [{:keys [key dev demo]} orphans]
        (println " -" key " dev:" (or dev "<missing>") " demo:" (or demo "<missing>")))))

  (doseq [{:keys [key dev demo]} (filter #(and (:dev %) (:demo %)) pairs)]
    (let [dev-name (fs/file-name dev)
          demo-name (fs/file-name demo)
          dev-content (slurp dev)
          demo-content (slurp demo)
          dev-lines (read-lines dev)
          demo-lines (read-lines demo)
          cross-in-demo (find-cross-env-leftovers demo-lines "dev" allow)
          cross-in-dev  (find-cross-env-leftovers dev-lines "demo" allow)
          docker-warns (concat
                         (check-image-policy :dev dev-name dev-content)
                         (check-image-policy :demo demo-name demo-content))
          diffs (normalized-diff demo dev demo-content dev-content)]

      (print-section (str "Pair: " demo-name "  <->  " dev-name))

      ;; Differences detected summary (this is what you asked for)
      (case (:kind diffs)
        :none
        (println "DIFF: none")

        :env-only
        (let [s (diff-stats (-> diffs :full :text))]
          (println (format "DIFF: env-only (after normalization: no diffs). hunks=%d +%d -%d"
                           (:hunks s) (:adds s) (:dels s))))

       :non-env
       (let [norm-text (-> diffs :norm :text)
             s (diff-stats norm-text)
             suspicious? (suspicious-nonenv-diff? norm-text)]
         (println (format "DIFF: NON-ENV (after normalization). hunks=%d +%d -%d [%s]"
                          (:hunks s) (:adds s) (:dels s)
                          (if suspicious? "SUSPICIOUS" "INFO")))

         ;; Always show it (this is what you want for numbers too)
         (println "\nFocused NON-ENV diff (normalized):")
         (println norm-text)

         ;; Only count as warning/failure if it's suspicious
         (when suspicious?
           (swap! warnings conj (str key ": suspicious non-env differences detected")))) 

        :error
        (do
          (swap! warnings conj (str key ": diff error"))
          (println "DIFF: error (diff command issue)")))

      ;; Print diffs if enabled
      (when show-diff
        (case (:kind diffs)
          :none nil

          :env-only
          (do
            (println "\nEnv-only diff (original files):")
            (println (-> diffs :full :text)))

          :non-env
          (do
            (println "\nNON-ENV DIFF (normalized copies) — start here:")
            (println (-> diffs :norm :text))
            (println "\nFull diff (original files) — context:")
            (println (-> diffs :full :text)))

          :error
          (println (-> diffs :full :text))))

      ;; Docker warnings
      (when (seq docker-warns)
        (swap! warnings into docker-warns)
        (doseq [w docker-warns]
          (println "DOCKER TAG WARNING:" w)))

      ;; Cross-env leftovers
      (when cross-in-demo
        (swap! warnings conj (str demo-name ": contains 'dev' outside allowlist"))
        (print-compact-cross "\nCROSS-ENV WARNING: 'dev' appears in demo file (outside allowlist):" cross-in-demo))

      (when cross-in-dev
        (swap! warnings conj (str dev-name ": contains 'demo' outside allowlist"))
        (print-compact-cross "\nCROSS-ENV WARNING: 'demo' appears in dev file (outside allowlist):" cross-in-dev))))

  (print-section "Summary")
  (if (empty? @warnings)
    (do
      (println "No warnings found.")
      (System/exit 0))
    (do
      (println "Warnings found:" (count @warnings))
      (doseq [w @warnings]
        (println " - " w))
      (System/exit 2))))
