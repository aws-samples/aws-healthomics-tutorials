// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.{QueryTest, Row}
import org.junit.runner.RunWith
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class ReferenceTest extends QueryTest with SharedSparkSession {

  test("Ensure that you can load a fasta index file and") {
    val colNames = List("NAME", "LENGTH", "OFFSET", "LINEBASES", "LINEWIDTH")
    val content = Row("chr1", 4, 6, 4, 5)
    val expected = content :: Nil
    val reference = Reference("src/test/resources/references/test.fasta")
    val indexDF = reference.parseIndex(spark)
    checkAnswer(indexDF, expected)
    assert(indexDF.columns === colNames)
  }

  test("Check for fasta file exists") {
    val reference = Reference("src/test/resources/references/test.fasta")
    assert(reference.exists())
  }

  test("Check for missing fasta file") {
    val reference = Reference("src/test/resources/references/does.not.exists")
    assert(reference.exists() === false)
  }
}
