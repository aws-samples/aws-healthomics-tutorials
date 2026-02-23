// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models.vep

import com.amazon.vincent.job.VincentTestTraits
import com.amazon.vincent.job.models.Schema.{AnnotationsStructType, VepStruct}
import com.amazon.vincent.job.models.vep.VepDefaultField.{Allele, Consequence}
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.{Encoders, QueryTest}
import org.junit.runner.RunWith
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class VepEntryTest extends QueryTest with VincentTestTraits with SharedSparkSession {

  test("VepEntry case class matches schema") {
    val vepEntrySchema = Encoders.product[VepEntry].schema
    assertResult(VepStruct)(vepEntrySchema)
  }

  test("AnnotationField matches schema") {
    val annotationsFieldSchema = Encoders.product[AnnotationColumn].schema
    assertResult(AnnotationsStructType)(annotationsFieldSchema)
  }

  test("Creating VepEntry fromVepInfoValue") {
    val vepString =
      """T|intron_variant&non_coding_transcript_variant|stage4,T|intron_variant|"""

    val order: Array[VepField] = Array(Allele, Consequence, ExtraField("cancer_type"))
    val vepEntries = VepEntry.fromVepInfoValue(vepString, order)

    assertResult(Some("T"))(vepEntries(0).allele)
    assertResult(Seq("intron_variant", "non_coding_transcript_variant"))(
      vepEntries(0).consequence.get.seq)
    assertResult(Some(Map("cancer_type" -> "stage4")))(vepEntries(0).extras)
    assertResult(Some("T"))(vepEntries(1).allele)
    assertResult(Seq("intron_variant"))(vepEntries(1).consequence.get.seq)
    assertResult(Some(Map("cancer_type" -> "")))(vepEntries(1).extras)
  }

  test("Creating VepEntry missing values") {
    val vepString =
      """T|intron_variant&non_coding_transcript_variant|,||"""

    val order: Array[VepField] = Array(Allele, Consequence, ExtraField("cancer_type"))
    val vepEntries = VepEntry.fromVepInfoValue(vepString, order)

    assertResult(Some("T"))(vepEntries(0).allele)
    assertResult(Seq("intron_variant", "non_coding_transcript_variant"))(
      vepEntries(0).consequence.get.seq)
    assertResult(Some(Map("cancer_type" -> "")))(vepEntries(0).extras)
    assertResult(Some(""))(vepEntries(1).allele)
    assertResult(None)(vepEntries(1).consequence)
    assertResult(Some(Map("cancer_type" -> "")))(vepEntries(1).extras)
  }

  test("Values with comma return empty array") {
    val vepString =
      """T|intron_variant&non_coding_transcript_variant|liver,lung,C|intron_variant|,||"""
    val order: Array[VepField] = Array(Allele, Consequence, ExtraField("cancer_type"))
    val vepEntries = VepEntry.fromVepInfoValue(vepString, order)
    assert(vepEntries.isEmpty)

  }
}
